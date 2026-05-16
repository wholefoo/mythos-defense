# Evaluation and Benchmarking Deep Dive

**Companion to the Mythos Defense Platform Blueprint**

---

## Why This Document Exists

A security platform without evaluation is a liability. Every other document in this series describes how to build something; this one describes how to know whether what you built actually works, whether it is getting better over time, and whether specific changes (new prompts, new models, new agent configurations) improve or degrade performance.

The stakes are concrete. Customers will rely on this platform's output to decide whether to ship code. Regulators may rely on it for compliance attestations. If the platform misses a critical vulnerability, the consequences land on real systems and real users. "We tested some examples and it seemed to work" is not a defensible position.

The evaluation problem is also genuinely hard. Mythos saturated Anthropic's own Cybench CTF benchmark at 100%, forcing their red team to shift to real-world zero-day discovery as the only meaningful evaluation left. AISLE's research showed that the capability frontier across security tasks is jagged — no single model dominates, and rankings reshuffle completely across tasks. This means evaluation cannot be reduced to a single number, and benchmarks go stale quickly.

This document lays out an evaluation methodology that is honest about these difficulties and produces trustworthy signal anyway.

---

## Design Principles

**Measure what matters, not what is easy.** Latency and token counts are easy to measure and meaningful, but they are not the core question. The core question is whether the platform finds the vulnerabilities it should find and avoids false alarms.

**Use multiple evaluation signals.** No single benchmark captures the full picture. Combine synthetic tests, replayed real-world vulnerabilities, adversarial evaluation, and production signal.

**Assume benchmarks will saturate.** Any static benchmark will eventually be memorized or optimized against. Plan for continuous refresh of evaluation data.

**Separate detection from exploitation from remediation.** Each is a distinct capability with its own failure modes. Aggregate scores hide the pattern.

**Track regressions as seriously as improvements.** A new prompt that catches more vulnerabilities but introduces false positives may be net negative. Always compare across multiple metrics simultaneously.

**Evaluate the whole pipeline, not just the agents.** The orchestrator, the sandbox, the tooling integrations — all contribute to outcomes. End-to-end evaluation catches what unit evaluation misses.

---

## The Ground Truth Problem

Before anything else: how do you know what the correct answer is?

For security evaluation, there are four sources of ground truth, each with different trust levels:

### Level 1: Known-patched CVEs

A CVE that has been disclosed, patched, and triaged has the highest ground truth quality. You know the vulnerability existed, where it was, what class it belonged to, and what the fix looked like. Replay evaluation (described below) uses this as its foundation.

### Level 2: Synthetic injection

You take clean code and deliberately introduce a known vulnerability. Ground truth is perfect because you created it, but ecological validity is limited — synthetic bugs may not look like real bugs.

### Level 3: Expert panel adjudication

For cases where ground truth is unclear, a panel of independent security experts reviews findings and votes. Slow, expensive, and has inter-rater reliability issues, but necessary for evaluating novel findings.

### Level 4: Production outcomes

In production, ground truth comes from what attackers actually exploit, what downstream tools independently confirm, and what customers confirm as real or false. This is the most ecologically valid signal but arrives slowly and incompletely.

The evaluation methodology uses all four, weighted by trust level.

---

## Metrics Taxonomy

Four metric families, each measured independently:

### Detection Metrics

Measures whether the platform finds vulnerabilities that exist.

- **True positive rate (recall)** by vulnerability class. Of the vulnerabilities known to exist in a test set, what fraction does the platform detect?
- **False positive rate** by vulnerability class. Of the vulnerabilities the platform reports, what fraction do not actually exist?
- **Precision.** True positives divided by all reports.
- **F1 score.** Harmonic mean of precision and recall.
- **Coverage.** What fraction of the identified threat model items received explicit Red Team attempts?
- **Time to first detection.** How long from the start of a Red Team session until the first valid finding is reported?

Detection metrics are tracked by vulnerability class, not aggregated. A platform that excels at SQLi but misses authentication bypasses has a coverage problem that an aggregate score hides.

### Exploitation Metrics

Detection without exploitation is a theoretical finding. These metrics measure whether reported findings are genuinely exploitable.

- **PoC success rate.** Of findings reported with a PoC, what fraction reproduce successfully when replayed?
- **Exploit quality score.** Expert-adjudicated grade on PoC clarity, determinism, and realism.
- **Time to exploit.** How long from detection to a working PoC?
- **Chain depth.** For multi-stage exploits, how many primitives were successfully chained?
- **Severity accuracy.** Does the platform's assigned severity match expert consensus? Tracked as percentage exact match and percentage within one severity level. (Anthropic reports 89% exact and 98% within-one for their own findings.)

### Remediation Metrics

Measures whether the Blue Team produces correct patches.

- **Patch correctness.** Does the patch actually block the reported PoC?
- **Regression rate.** What fraction of patches introduce new test failures?
- **Semantic preservation.** Does the patched code retain legitimate functionality? Measured by property-based tests and integration tests.
- **Patch quality score.** Expert-adjudicated grade on idiomaticity, minimality, and architectural soundness.
- **New-vulnerability rate.** What fraction of patches introduce new exploitable issues? (A patch that fixes SQLi but adds an XSS is a net-negative outcome.)
- **Iteration count to correct patch.** How many Blue Team attempts were needed before VERIFY passed?

### System Metrics

Measures the platform as infrastructure.

- **Workflow completion rate.** Fraction of workflows that reach a terminal state without operator intervention.
- **End-to-end latency distributions.** p50, p95, p99 for each workflow shape.
- **Cost per finding.** Total workflow cost divided by valid findings produced.
- **Cost per fixed vulnerability.** Total cost divided by vulnerabilities that exit the loop patched.
- **Budget overrun rate.** Fraction of workflows that hit budget caps.
- **Agent error rate.** Fraction of agent sessions that terminate with errors.
- **Sandbox incident rate.** Fraction of sessions with any detected sandbox anomaly.

---

## Evaluation Suites

The platform maintains multiple evaluation suites, each serving a distinct purpose.

### Suite 1: Known-Vulnerable Applications

Deliberately vulnerable applications used as smoke tests and regression baselines.

| Application | Language | Classes covered |
|------------|----------|-----------------|
| OWASP Juice Shop | Node.js | Broad OWASP Top 10 |
| DVWA | PHP | Classic injection and XSS |
| WebGoat | Java | Authentication, authorization |
| Damn Vulnerable GraphQL | Node.js | GraphQL-specific flaws |
| NodeGoat | Node.js | OWASP Top 10 in Node context |
| Vulhub scenarios | Various | CVE reproductions |

These suites are included in every CI run. Regression on any of them is a release blocker.

Limitations: these apps are widely known, likely present in model training data, and do not represent realistic production code. They are necessary but not sufficient.

### Suite 2: CVE Replay

For each CVE in a curated set:

1. Check out the code at the commit immediately before the fix
2. Run the full platform workflow
3. Measure whether the platform identifies the vulnerability
4. Measure whether the platform's patch is equivalent to the real fix

Curation criteria: CVEs must be in languages and frameworks the platform supports, must have clear fix commits, and must be exploitable in a realistic context. Aim for at least 50 CVEs per language, balanced across severity and class.

Refresh cadence: quarterly. Add new CVEs as they become available; retire CVEs that have been heavily trained on.

### Suite 3: Synthetic Bug Injection

A clean, well-reviewed codebase (for example, an internal reference application) has known bug classes systematically injected. Each injection produces a test case with:

- The unmodified codebase
- The injected version
- The exact class, location, and expected detection of the bug
- A working exploit for validation

Bug classes include every Mythos-relevant category. Injections are parameterized — the same bug class can be injected at different locations, with different data flows, and with different levels of obfuscation.

Strength: perfect ground truth, unlimited generation, controllable difficulty. Weakness: synthetic bugs have subtle tells that real bugs don't — they may cluster at specific AST positions, use specific naming patterns, or exhibit other artifacts of the injection process.

Mitigation: use multiple injection strategies (manual, template-based, LLM-generated) and verify that detection rates are consistent across strategies.

### Suite 4: Adversarial Held-Out Set

A set of vulnerabilities maintained separately by a team with no access to the platform's prompts, training data curation, or evaluation tuning. This set is the "test set" that cannot be optimized against.

Updates to platform prompts or agent configurations are evaluated against this set periodically but not per-change. Frequent evaluation against held-out data leaks information and defeats the purpose.

Held-out set integrity requires organizational discipline. The team maintaining it must resist pressure to share details, even when engineers are debugging.

### Suite 5: Production Shadow Evaluation

In production, a fraction of workflows are selected for shadow evaluation. After the workflow completes, a separate pipeline:

- Runs additional Red Team configurations (different prompts, different models)
- Adjudicates the original findings against the alternative findings
- Flags discrepancies for human review
- Feeds discrepancy patterns back into prompt improvement work

Shadow evaluation is expensive and not run on every workflow. Sampling rate is tuned to cost budget and statistical significance requirements.

---

## Evaluation Methodology

### Per-Change Evaluation

Every change to the platform (prompt update, model switch, agent reconfiguration, tool change) goes through a gated evaluation:

1. **Smoke test.** Suite 1 must pass without regression. Fast, runs on every PR.
2. **Regression test.** Subset of Suite 2 and Suite 3. Runs on merge to main.
3. **Full regression.** All of Suite 1, 2, 3. Runs nightly.
4. **Held-out check.** Suite 4. Runs weekly or before releases.
5. **Shadow deployment.** New configuration runs in shadow mode in production for N workflows before becoming default.

Any regression beyond configured thresholds blocks the change until investigated.

### Threshold Configuration

Regression thresholds are set per metric and tightened over time. A reasonable starting point:

| Metric | Regression threshold |
|--------|---------------------|
| Overall recall | -2 percentage points |
| Overall precision | -3 percentage points |
| Any vulnerability class recall | -5 percentage points |
| PoC success rate | -5 percentage points |
| Patch correctness | -3 percentage points |
| Cost per finding | +15% |
| p95 latency | +20% |

Thresholds are tight enough that real regressions are caught and loose enough that random variation does not trigger constant blocks. Calibrate based on observed variance in steady state.

### Statistical Rigor

Comparisons between platform configurations require statistical testing, not eyeballing numbers:

- Use bootstrap confidence intervals, not point estimates
- Apply multiple-comparison correction when evaluating across many metrics
- Require effect sizes, not just p-values (a statistically significant 0.1% improvement probably does not justify deployment)
- Report variance and sample sizes in every evaluation report

Evaluation suites must be large enough to detect meaningful differences. A suite of 20 CVEs cannot reliably distinguish a 5% recall improvement from noise.

### Human Adjudication Workflow

Some evaluations require expert human judgment. The workflow:

1. Findings are anonymized (source configuration not revealed)
2. Three independent reviewers rate each finding on the relevant dimensions
3. Disagreements beyond a threshold are escalated to a senior reviewer
4. Inter-rater reliability is tracked; low agreement indicates rubric ambiguity
5. Adjudicated results flow back into the evaluation corpus

Human adjudication is slow and expensive. Reserve it for high-signal evaluations: novel finding quality, patch quality, and held-out set scoring.

---

## Specific Evaluation Scenarios

### Evaluating a New Red Team Prompt

Scenario: prompt engineer proposes changes to the Red Team Agent system prompt.

Evaluation:

1. Run old and new prompts on Suite 1 (smoke test) in parallel. Both must pass.
2. Run both on a matched sample from Suite 3, 50 injections per vulnerability class.
3. Compute per-class recall, precision, and PoC success rate with confidence intervals.
4. Run both on a small Suite 2 sample. Compare severity accuracy.
5. If results look promising, schedule held-out evaluation.
6. After held-out confirms, deploy in shadow for 1,000 production workflows.
7. After shadow, promote to default.

Total elapsed time for a significant prompt change: two to three weeks. The long cycle is intentional. Prompt engineering is high-leverage and error-prone; rushing it produces regressions that are discovered by customers.

### Evaluating a New Model

Scenario: a newer Claude model is released. Should it replace the current Red Team model?

Evaluation:

1. Re-run all of Suite 1, 2, 3 against new model with current prompts.
2. Compare cost and latency distributions.
3. If new model is strictly better on quality metrics, deploy. If it is better on some and worse on others (common), make an explicit tradeoff decision with documented rationale.
4. Specifically check whether prompts need to be re-tuned for the new model. Old prompts may be overfit to old model quirks.
5. Run adversarial evaluation: specifically test whether the new model has different failure modes (different refusal patterns, different context utilization, different tool-use styles).

### Evaluating Platform Effectiveness Against a Real Threat

Scenario: a new vulnerability class is observed in the wild. Does the platform catch it?

Evaluation:

1. Reproduce the vulnerability class in a test codebase.
2. Run the platform. Does Red Team find it?
3. If yes: verify the finding quality, verify the patch. Add this case to Suite 3.
4. If no: root-cause the failure. Is it a prompt issue, a tool gap, a model limitation, or a threat model gap? Address the root cause, not the symptom.
5. Add regression test to prevent future regression.

This scenario drives much of the platform's long-term improvement. Real-world vulnerabilities surface gaps that synthetic suites miss.

---

## Benchmarking Against External References

The platform's performance should be benchmarked against external reference points periodically.

### Against Traditional Tools

Run the platform and traditional SAST tools (CodeQL, Semgrep) on the same codebases. Measure:

- Vulnerabilities found by the platform that traditional tools missed
- Vulnerabilities found by traditional tools that the platform missed
- False positive rates compared
- Time to scan compared
- Total cost compared

The honest framing is complement, not replacement. The platform's value proposition is catching vulnerabilities pattern-matching tools miss, not exceeding them on pattern-matched bugs. Both tools in the stack makes sense for most customers.

### Against Expert Humans

Periodically, commission independent security researchers to audit codebases that the platform has also scanned. Compare findings. Measure:

- Agreement rate on high-severity findings
- Bugs humans found that the platform missed
- Bugs the platform found that humans missed
- Time and cost for each approach

Expect humans to find things the platform missed, especially subtle logic flaws and business-specific issues. Expect the platform to find things humans missed, especially in large codebases where attention is the limiting factor.

### Against Published Benchmarks

Where published benchmarks exist (SWE-bench, CyberGym, CTI-REALM), report scores. Acknowledge the saturation problem: these benchmarks are being optimized against industry-wide and eventually lose signal. Use them for reference, not as primary metrics.

Do not overfit to published benchmarks. A platform that leads SWE-bench by 10% and produces worse customer outcomes is a failed optimization.

---

## Confidence Reporting to Customers

Customers receive a confidence score with each workflow report. This score must be honest.

### What the Score Represents

The confidence score reflects:

- How many adversarial iterations converged cleanly
- Coverage of the threat model
- Severity distribution of historical findings on the codebase
- Known limitations of the configuration used
- The platform's performance on similar codebases in evaluation

### What It Does Not Represent

The score is not a probability that no vulnerabilities exist. It is a measure of how hard the platform tried. Communicate this clearly:

> "Confidence: High. The platform completed 5 adversarial iterations with no new findings, covered 100% of the identified threat model items, and used a configuration that historically achieves 85% recall on similar codebases. This does not guarantee the code is free of vulnerabilities; it indicates that vulnerabilities the platform is capable of finding, with the effort configured, were either found and addressed or not present."

Customers who understand the score can use it. Customers who misread it as a guarantee will be disappointed, sometimes catastrophically. Clarity here is a product quality issue, not a legal one.

### Known-Unknown Reporting

The report also discloses what the platform is known to be weak at. If the current configuration has low recall on race conditions, say so. If crypto-library review was out of scope, say so. Customers making risk decisions need to know what was not checked.

---

## Continuous Evaluation in Production

Evaluation does not stop at release. In production:

### Feedback Collection

- Customers can flag findings as false positives or confirm true positives
- Post-deployment incident data (if shared) flows back as ground truth
- Security disclosures from customers' downstream tools provide signal
- Patch adoption rates indicate finding actionability

### Drift Detection

Platform performance can drift due to model updates, dependency changes, or evolving codebase patterns. Detect drift by:

- Running Suite 1 and Suite 2 continuously in production
- Alerting on metric deviations beyond configured bounds
- Tracking per-customer metrics to catch tenant-specific drift (some customers' codebases may exercise the platform differently)

### Evaluation Data Lifecycle

Evaluation data itself must be managed:

- Rotate held-out sets at least annually
- Track which data has been used for what purpose, to prevent contamination
- Version evaluation suites; report which version was used for any given measurement
- Archive historical evaluation runs for long-term trend analysis

---

## Failure Modes to Watch For

### Overfitting to Benchmarks

If a platform version's performance rises rapidly on specific benchmarks but does not rise on held-out data, it is overfitting. Likely causes: benchmark data leakage into prompts, evaluation-driven tuning that generalizes poorly. Response: rotate benchmarks, investigate prompt changes.

### The Confident Wrong Answer

Models can produce highly confident false findings. These are worse than low-confidence false findings because they consume human review effort. Monitor the correlation between platform confidence and ground-truth correctness. If confidence is not well-calibrated, recalibrate.

### Sudden Degradation

A model update, a prompt regression, or a tool change can sharply degrade performance. Continuous evaluation catches this; alerting on performance drops is as important as alerting on availability drops.

### Evaluation Theater

Teams can fall into the trap of running evaluations that produce nice-looking numbers but don't actually measure what matters. Periodically audit: does passing the evaluation suite correspond to customer outcomes? If a release passes all evaluations but customers report problems, the evaluations are wrong and must be revised.

### Benchmark Sycophancy

The platform is measured by humans; humans are subject to motivated reasoning. If the team building the platform is also choosing which metrics to emphasize, choose at least some metrics by committee or by external party. Ensure someone in the organization is professionally motivated to find evaluation flaws.

---

## Relationship to Platform Development

Evaluation is a first-class engineering function, not a QA step:

- Every engineer working on agents understands the evaluation methodology
- New agent capabilities come with new evaluation suites
- Evaluation improvements are roadmapped alongside feature development
- Evaluation team has independence and resources to push back on premature deployment

The evaluation function reports outside the development organization in mature implementations. A VP of Engineering whose bonus depends on shipping is not the right owner of evaluation. Tension between ship-it and prove-it is productive; remove it and the platform ships regressions.

---

## What "Done" Looks Like

The evaluation methodology is sufficient when:

- Every metric in the taxonomy has a defined measurement procedure and current value
- Held-out evaluation is genuinely held out, with organizational enforcement
- Regression is caught within hours of introduction, not after customer reports
- Confidence scores reported to customers are calibrated (predicted probability matches observed frequency)
- New agent versions ship with published evaluation results comparing to prior version
- The platform team can answer "how do we know this works?" with evidence, not vibes

Evaluation is never truly done. New vulnerability classes emerge. Models change. Adversaries adapt. The evaluation methodology must evolve with them, or the numbers stop meaning anything.

---

## Closing Thought

The Mythos announcement was so striking partly because Anthropic published specific, verifiable capabilities: a 27-year-old OpenBSD bug, a 17-year-old FreeBSD RCE, 72.4% exploit success on Firefox, 181-to-2 improvement over the prior model. These claims were evaluable. Some researchers (notably AISLE) immediately ran their own evaluations and found nuance the headline numbers obscured.

A platform that claims to defend against this class of threats will be held to the same standard. Customers, researchers, and competitors will evaluate it. The question is not whether evaluation happens but whether the platform's own internal evaluation produces honest numbers before external evaluation does.

Build the evaluation before you need it. The alternative is learning the platform's limitations from public research, which is the expensive path.

---

*Document version 1.0 — companion to mythos-defense-platform-blueprint.md, mythos-defense-platform-deep-dive.md, mythos-defense-platform-sandboxing.md, and mythos-defense-platform-orchestrator.md*
