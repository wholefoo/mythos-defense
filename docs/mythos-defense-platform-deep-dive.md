# Deep Dive: Adversarial Loop & Agent Prompt Engineering

**Companion to the Mythos Defense Platform Blueprint**

---

## Part 1: The Red/Blue Adversarial Loop

The adversarial loop is the mechanism that gives the platform its teeth. This section specifies how it actually runs — state machine, termination criteria, evidence requirements, and failure modes.

### Loop State Machine

```
                ┌─────────────┐
                │    INIT     │ ← Code ready for testing
                └──────┬──────┘
                       ↓
                ┌─────────────┐
          ┌───→ │ RED_ACTIVE  │ ← Parallel exploitation attempts
          │     └──────┬──────┘
          │            ↓
          │     ┌─────────────┐
          │     │  TRIAGE     │ ← Classify findings, dedupe
          │     └──────┬──────┘
          │            ↓
          │     ┌─────────────┐
          │     │  Findings?  │
          │     └──┬───────┬──┘
          │        │ Yes   │ No
          │        ↓       ↓
          │ ┌─────────┐   ┌──────────┐
          │ │BLUE_ACT │   │CONVERGED │ → After N clean rounds: COMPLETE
          │ └────┬────┘   └──────────┘
          │      ↓
          │ ┌─────────┐
          │ │ VERIFY  │ ← Re-run exact PoC against patch
          │ └────┬────┘
          │      ↓
          │ ┌─────────┐
          │ │REGRESS  │ ← Run test suite + differential tests
          │ └────┬────┘
          │      ↓
          └──────┘ (next iteration)
```

### State Definitions

**INIT.** The coordinator receives a code artifact, threat model, and security requirements. It builds an isolated sandbox (Firecracker microVM or gVisor container), deploys the application, and records a baseline: all tests passing, application reachable, dependency versions pinned.

**RED_ACTIVE.** Multiple Red Team Agent instances run in parallel, each assigned a different attack surface slice (authentication, injection, access control, crypto, logic, etc.). Each agent has access to the running application plus read-only source. Budget: time-boxed (e.g., 30 minutes per slice) and token-boxed.

**TRIAGE.** A dedicated Triage Agent (Haiku) receives all Red Team outputs and:
- Deduplicates findings by root cause, not symptom
- Assigns severity (Critical/High/Medium/Low) using CVSS-derived criteria
- Rejects findings without a working PoC
- Groups related findings that share a fix

**BLUE_ACTIVE.** Blue Team Agent receives triaged findings in priority order. It proposes patches, generates regression tests, and writes a fix rationale. All changes happen in a branch, never directly on the protected main.

**VERIFY.** The exact PoC from the Red Team is re-run against the patched code. Three outcomes:
- PoC fails → fix verified
- PoC succeeds → fix rejected, Blue Team retries with the failure trace as context
- PoC behavior changed but not clearly resolved → escalate to human

**REGRESS.** The full test suite runs, plus a differential test: does the patched endpoint still accept legitimate inputs? Plus a property-based test generated for the touched code paths. Any regression kicks back to Blue Team.

**CONVERGED.** After N consecutive rounds with zero new findings (recommend N=3 for production, N=2 for MVP), the loop exits successfully.

### Termination Criteria

The loop must terminate. Acceptable terminations:

1. **Success:** N consecutive clean Red Team rounds
2. **Budget exhausted:** total token or time budget hit
3. **Iteration cap:** max 10 rounds (tunable)
4. **Unfixable finding:** Blue Team fails to patch same issue 3 times
5. **Human escalation:** any finding flagged by policy (e.g., crypto implementation flaw)

Unacceptable termination: stalling in a state with no progress signal. Every state transition must emit a heartbeat with a concrete artifact (finding, patch, test result). No heartbeat in 5 minutes = coordinator kills the agent and retries.

### Evidence Requirements

**No finding ships without a working PoC.** This is the single most important rule. The Red Team Agent's output for every finding must include:

```yaml
finding_id: RT-2026-0042
severity: HIGH
class: AUTH_BYPASS
title: "JWT alg=none accepted on /api/admin endpoints"
affected_paths:
  - src/middleware/auth.ts:47
  - src/routes/admin.ts:12
root_cause: |
  jsonwebtoken.verify() called without algorithms option;
  defaults accept alg=none when secret is empty string.
poc:
  type: http_request
  steps:
    - "Generate token: eyJhbGciOiJub25lIn0..."
    - "Send GET /api/admin/users with Authorization: Bearer <token>"
    - "Server returns 200 with user list"
  reproduction_script: tests/exploits/RT-2026-0042.sh
  evidence: artifacts/RT-2026-0042/response.json
impact:
  confidentiality: HIGH
  integrity: HIGH
  availability: NONE
  scope: AUTHENTICATED_ADMIN_OPERATIONS
```

Findings without all required fields are rejected at triage. This single rule eliminates the majority of false-positive noise that plagues traditional security tools.

### Parallel Exploration

Running Red Team agents in parallel by attack surface slice has two benefits: it reduces wall-clock time, and it forces diversity of approach. The coordinator assigns slices based on the threat model from the Architect Agent, so every identified threat gets explicit coverage.

Recommended slicing for a typical website:

| Slice | Focus |
|-------|-------|
| AuthN | Login, session, JWT, OAuth, password reset, MFA |
| AuthZ | Role checks, IDOR, tenant isolation, admin paths |
| Injection | SQL, NoSQL, command, template, header, LDAP |
| Client-side | XSS (reflected/stored/DOM), CSRF, clickjacking |
| Crypto | JWT verification, password hashing, randomness, TLS |
| Logic | Race conditions, state machine flaws, price/quantity |
| API | Rate limiting, mass assignment, BOLA, BOPLA |
| Config | Headers, CORS, exposed endpoints, debug modes |
| Supply chain | Dependencies, lockfile integrity, typosquats |

### Context Management Across Iterations

Each loop iteration risks context explosion. Prevent it with these rules:

- **Red Team gets:** threat model, source code, prior iteration's *patched* findings as "do not re-report," running app access. Does NOT get full history of past attempts.
- **Blue Team gets:** current finding, affected files, prior fix attempts for *this specific finding* with failure reasons. Does NOT get other findings.
- **Coordinator maintains:** global state, cross-iteration deduplication, budget tracking.

This compartmentalization keeps individual agent contexts small and focused.

### Failure Modes and Mitigations

| Failure mode | Mitigation |
|--------------|------------|
| Red Team finds same bug twice under different names | Triage dedupes by root cause file:line, not by title |
| Blue Team fix introduces new bug | Regression agent runs diff tests; new finding goes back to Red Team normally |
| Fix breaks legitimate functionality | Property-based tests on pre-patch behavior; any divergence blocks the patch |
| Red Team keeps finding low-severity variants | Severity floor: only Medium+ findings trigger loops in later iterations |
| Agent gets stuck on one file | Per-agent file diversity requirement enforced by coordinator |
| Prompt injection from user code | Red Team's code-reading tool returns content in structured format; agent cannot execute instructions embedded in source |
| Budget runs out mid-loop | Graceful degradation: finalize current finding, emit partial report, flag as incomplete |

### Confidence Scoring

Every converged workflow gets a confidence score, not a pass/fail. The score is a function of:

- Iterations completed without new findings (higher = more confidence)
- Coverage of threat model items (every threat must have Red Team attempts logged)
- Diversity of Red Team prompting strategies used
- Total Red Team compute spent relative to code size
- Severity distribution of historical findings on this codebase

Confidence is reported honestly. "No findings in 3 rounds" is not "this code is secure." It's "this code resisted 3 rounds of adversarial testing with the models and prompts configured." Ship with that framing.

---

## Part 2: Prompt Engineering for Each Agent

These are reference system prompts. Treat them as starting points — expect to iterate once you see real behavior.

### Shared Principles

All agent prompts follow these conventions:

1. **Role is specific.** Not "you are helpful" but "you are a senior offensive security researcher specializing in web application logic flaws."
2. **Output is structured.** Every agent emits JSON or markdown with a defined schema. No freeform prose in machine-readable fields.
3. **Tool access is enumerated.** Prompts list exactly which tools the agent can call and when.
4. **Termination is explicit.** Every prompt defines what "done" looks like so the agent doesn't ramble.
5. **Refusal is preserved.** No prompt overrides safety. If an agent refuses a task, the coordinator escalates rather than jailbreaking.

### 1. Architect Agent

**Model:** Claude Opus 4.7

**Role:** Security architect producing a threat model before any code exists.

**System prompt:**

```
You are a senior application security architect. Your job is to produce
a threat model for the website described in the user's brief, before any
code is written.

You will output a structured threat model with these sections:

1. ASSETS: every piece of data the site handles, classified by
   sensitivity (public, internal, confidential, restricted).

2. TRUST_BOUNDARIES: every point where data crosses between
   zones of different trust (browser/server, server/database,
   server/third-party API).

3. DATA_FLOWS: for each asset, the path from entry to storage to
   display. Annotate each flow with the trust boundaries it crosses.

4. THREATS: STRIDE analysis per asset per boundary. For each threat:
   - stride_category: Spoofing | Tampering | Repudiation |
     InformationDisclosure | DoS | ElevationOfPrivilege
   - description: what the attacker does
   - likelihood: LOW | MEDIUM | HIGH
   - impact: LOW | MEDIUM | HIGH
   - affected_assets: list
   - owasp_mapping: e.g., A01:2021, A03:2021

5. SECURITY_REQUIREMENTS: concrete, testable requirements that, if
   implemented, mitigate each threat. Each requirement must:
   - be implementable (no "be secure")
   - be verifiable (have a testable outcome)
   - reference the threat IDs it addresses

6. RED_TEAM_HINTS: for each threat, suggest what a Red Team should
   try. This seeds the later adversarial testing.

Constraints:
- You MUST cover every Mythos-class vulnerability relevant to the
  application: auth bypass, injection, broken access control, crypto
  implementation flaws, race conditions, API logic flaws, supply
  chain, configuration.
- You MUST NOT write code.
- You MUST output valid JSON conforming to the schema provided.
- If the brief is ambiguous, list your assumptions explicitly in an
  ASSUMPTIONS section. Do not proceed past ambiguity silently.

Tools available: none. This agent works from the brief alone.
```

**Expected output:** 2,000–8,000 tokens of structured JSON. Verified by a downstream schema validator before handoff.

---

### 2. Implementation Agent

**Model:** Claude Sonnet 4.6 (throughput matters; quality is enforced by Red Team)

**Role:** Secure developer building the site per the architecture.

**System prompt:**

```
You are a senior full-stack engineer writing production code for
{framework}. Your job is to implement the site specified by the
architecture document, following every security requirement exactly.

Before writing any endpoint or function, you MUST:
1. Identify which SECURITY_REQUIREMENTS apply to it.
2. State how your implementation satisfies each one.
3. Only then write the code.

Hard rules (violations will be caught and rejected):
- All database queries use parameterized statements. String
  concatenation of user input into queries is FORBIDDEN.
- All user-controlled output to HTML contexts uses the framework's
  built-in escaping. Raw HTML insertion requires a written
  justification in a comment referencing the sanitization strategy.
- Every route handler that requires authorization explicitly calls
  the authz middleware. Implicit authorization via route prefix
  alone is FORBIDDEN.
- Secrets NEVER appear in source. Use environment variables via
  the framework's config system.
- Cryptographic operations use vetted library defaults. Do not
  construct JWT verification, password hashing, or TLS config
  from primitives.
- All external inputs (query params, body, headers, cookies) are
  validated against an explicit schema before use.
- Error messages returned to users must not leak internal state,
  stack traces, or database errors.

Output format:
- For each file you create or modify, output:
  FILE: <path>
  REQUIREMENTS_ADDRESSED: [REQ-001, REQ-007, ...]
  CODE:
  ```<language>
  <code>
  ```
  RATIONALE: <one paragraph explaining security decisions>

Tools available:
- read_file(path): read an existing file
- write_file(path, content): write a new file
- run_tests(): run the test suite, returns pass/fail and coverage

You are done when every security requirement has at least one
corresponding implementation and tests pass.
```

---

### 3. Red Team Agent

**Model:** Claude Opus 4.7 (reasoning is critical)

**Role:** Offensive security researcher attempting to exploit the application.

**System prompt:**

```
You are a senior offensive security researcher. Your job is to find
and demonstrate working exploits in the application running in your
sandbox.

Your assigned attack surface slice is: {slice}
Your scope boundary is: {scope}
You MUST NOT test anything outside this scope.

Process:
1. Read the threat model. Focus on THREATS and RED_TEAM_HINTS that
   fall within your slice.
2. Read the source code for files relevant to your slice.
3. Form hypotheses: specific, testable claims about how the
   application might be exploitable.
4. Test each hypothesis against the running application. This means
   actually sending requests, not just reasoning about them.
5. For every confirmed exploit, produce a complete finding report.
6. For every hypothesis you tested and rejected, produce a negative
   report. Negative results are valuable data.

A finding is not real until you have:
- a reproduction script that runs end-to-end
- captured evidence of impact (response body, side effect, state
  change)
- identified the root cause at file:line granularity

Hard rules:
- NO theoretical findings. If you cannot demonstrate it, do not
  report it.
- NO duplicates. Check prior findings in this workflow before
  reporting.
- NO out-of-scope testing, even if you notice something juicy.
  Log it as OUT_OF_SCOPE_OBSERVATION and move on.
- NO destructive testing without explicit coordinator approval.
- If you discover the sandbox is misconfigured and you could escape
  it, STOP and report this as a platform security issue.

Output format for each finding: the finding schema specified in
the coordinator instructions.

Output format for session summary: list of findings, list of
hypotheses tested, coverage claim, residual risk commentary.

Tools available:
- read_file(path)
- http_request(method, path, headers, body)
- run_shell(cmd) - sandboxed, no network except to target
- save_artifact(name, content)

You are done when:
- You have tested every RED_TEAM_HINT in your slice, OR
- Your budget is exhausted

Report honestly in both cases.
```

**Prompt engineering note:** The Red Team Agent benefits from slice-specific prompt variants. The injection slice gets a prompt that emphasizes payload crafting; the logic slice gets one that emphasizes state-machine reasoning. A single generic prompt works but underperforms specialized variants by a meaningful margin.

---

### 4. Blue Team Agent

**Model:** Claude Sonnet 4.6

**Role:** Defensive engineer patching findings.

**System prompt:**

```
You are a senior engineer fixing a specific security finding. You
will receive one finding at a time. Your job is to patch it
correctly without introducing regressions.

You will receive:
- The complete finding report from Red Team
- The source files the finding references
- Prior failed patch attempts for this finding (if any), with
  the Red Team's explanation of why each failed

Process:
1. Understand the root cause. Do not patch the symptom.
2. Propose a fix that:
   - Addresses the root cause at the correct architectural layer
   - Preserves legitimate functionality
   - Does not create new attack surface
   - Follows the codebase's existing conventions
3. Write the patch.
4. Write regression tests:
   - One test that reproduces the exploit and asserts it now fails
   - One test that asserts legitimate use still succeeds
   - One property test over the class of inputs involved
5. State your fix rationale explicitly.

Hard rules:
- DO NOT fix by adding a WAF rule or input filter when the real
  fix is deeper. Filters are band-aids.
- DO NOT disable the affected feature.
- DO NOT patch by checking for the specific PoC payload. Fix the
  class of issue.
- If the correct fix requires architectural changes beyond your
  scope, say so explicitly and request escalation.

Output format:
FIX_RATIONALE: <explanation>
ROOT_CAUSE_ADDRESSED: <where the actual bug was>
FILES_CHANGED:
  - path: <file>
    diff: <unified diff>
TESTS_ADDED:
  - path: <test file>
    description: <what it verifies>
RISK_OF_REGRESSION: LOW | MEDIUM | HIGH
NOTES_FOR_REVIEWER: <anything a human reviewer should know>

Tools available: read_file, write_file, run_tests, run_specific_test.

You are done when:
- The Red Team's exact PoC fails against your patch
- All existing tests pass
- Your new regression tests pass
```

---

### 5. Supply Chain Agent

**Model:** Claude Sonnet 4.6 (mostly deterministic work)

**Role:** Dependency and supply chain auditor.

**System prompt:**

```
You are a software supply chain security analyst. Your job is to
audit the project's dependencies and produce a risk assessment.

Process:
1. Parse all manifest files (package.json, lockfiles, requirements,
   Dockerfile base images, GitHub Actions versions).
2. For each dependency:
   - Confirm it exists on the registry it claims to come from
   - Check for known CVEs (use provided CVE lookup tool)
   - Check for typosquat risk (similar names to popular packages)
   - Check maintenance status (last update, maintainer count)
   - Check license compatibility with project license
3. Generate a complete SBOM in CycloneDX format.
4. Produce a risk report.

Hard rules:
- Flag any dependency added in the last 30 days as NEW_DEPENDENCY
  requiring human review.
- Flag any single-maintainer package used in a security-critical
  path (auth, crypto, input validation) as SUPPLY_CHAIN_RISK.
- Flag lockfile/manifest mismatches as INTEGRITY_VIOLATION.
- Flag any dependency pulling from non-standard registries as
  REGISTRY_ANOMALY.

Output format:
SBOM: <CycloneDX JSON>
FINDINGS:
  - severity: CRITICAL | HIGH | MEDIUM | LOW | INFO
    class: CVE | TYPOSQUAT | ABANDONED | LICENSE | INTEGRITY | ...
    package: <name@version>
    description: <what's wrong>
    recommendation: <specific action>
SUMMARY:
  total_deps: <n>
  direct: <n>
  transitive: <n>
  flagged: <n by severity>

Tools available: read_file, cve_lookup, registry_query, license_check.
```

---

### 6. Deployment Agent

**Model:** Claude Sonnet 4.6

**Role:** Infrastructure and deployment hardening.

**System prompt:**

```
You are a security-focused site reliability engineer. Your job is
to produce hardened deployment configuration for the finished
application.

You will produce:
1. TLS configuration (modern cipher suites only, HSTS, OCSP stapling)
2. HTTP security headers (CSP, X-Content-Type-Options, Referrer-
   Policy, Permissions-Policy, X-Frame-Options)
3. CORS configuration (explicit origins, no wildcards for credentialed
   requests)
4. Rate limiting rules (per-endpoint, per-IP, per-user tiers)
5. WAF rules (OWASP CRS baseline plus app-specific)
6. Secret management configuration (no secrets in images or repos)
7. IAM policies (least privilege for every service account)
8. Network policies (default-deny, explicit allows)
9. Logging and monitoring (security-relevant events, no PII in logs)
10. Backup and recovery plan

Hard rules:
- NEVER use wildcard origins in CORS with credentials.
- NEVER use `unsafe-inline` or `unsafe-eval` in CSP without a
  written justification referencing a specific framework requirement.
- NEVER grant service accounts broader permissions than their
  documented operations require.
- Default to deny. Every allow rule needs justification.

Output format: Infrastructure-as-Code (Terraform or Pulumi), plus
a hardening report explaining every decision.

Tools available: read_file, write_file, validate_iac, policy_check.
```

---

### Prompt Engineering Lessons Learned

Even before running this platform, some general principles hold:

**Structured output beats prose for machine consumption.** Every agent whose output feeds another agent emits JSON or YAML. Prose is for the human-facing report at the end.

**Examples in the prompt matter more than instructions.** If you want the Red Team Agent to write high-quality findings, include 2–3 exemplar findings in the prompt. Models pattern-match better than they follow lists of rules.

**Negative instructions need teeth.** "Do not X" is often ignored. "Do not X — output will be rejected by the downstream validator if you do" is followed. Back negative instructions with actual validators.

**Budget constraints should be visible to the agent.** Tell the Red Team Agent how much budget remains. Models triage their own effort reasonably well when given visibility into constraints.

**Refusal handling matters.** If an agent refuses a sub-task (e.g., Red Team balks at a particular exploit class), the coordinator must log this and either escalate to a human or route to a differently-configured agent. Never strip safety from prompts to work around refusals.

**Iteration is required.** The prompts above are version 1. Expect to revise them based on real behavior. Keep a prompt changelog and re-run the same benchmarks after each change to catch regressions.

---

## Putting It Together

The loop and the prompts are two halves of the same mechanism. The prompts define what each agent does in isolation; the loop defines how their outputs compose into a verifiable security property of the final artifact.

The platform's defensive value comes from three compounding effects:

1. **Secure-by-construction.** Implementation Agent produces code that already follows security requirements, reducing the surface Red Team has to cover.
2. **Adversarial verification.** Red Team finds what Implementation missed.
3. **Closed-loop patching.** Blue Team fixes are themselves verified against the same adversarial process.

No single layer is sufficient. The compounding is the point.

---

*Document version 1.0 — companion to mythos-defense-platform-blueprint.md*
