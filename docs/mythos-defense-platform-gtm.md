# Go-to-Market and Positioning Deep Dive

**Companion to the Mythos Defense Platform Blueprint**

---

## Why This Document Exists

The technical architecture in the preceding documents is buildable. Whether it should be built as a product, sold as a product, and scaled as a business is a separate question. Plenty of technically correct platforms have failed commercially because the market, the positioning, or the pricing was wrong.

This document addresses the commercial question directly. It describes who buys this, why they buy it instead of alternatives, how it is priced, how it is sold, and what could kill it as a business. It is written to be honest about the competitive pressures, particularly the uncomfortable fact that Anthropic itself offers a product in an adjacent space.

---

## The Market Context

### The Forcing Function

The post-Mythos security landscape creates genuine buying pressure. Wiz estimates 12–18 months before open-source models reach parity with Mythos-class capabilities. Corelight and others have framed this as the collapse of the exploitation window — the gap between vulnerability disclosure and weaponization, historically measured in weeks, is compressing to hours. Security teams that relied on patch cycles to keep up are running out of runway.

Anthropic's own positioning around Project Glasswing acknowledges that these capabilities will reach attackers regardless of Anthropic's release decisions. The question buyers face is not whether AI-native security tools will become necessary but which ones to adopt, from which vendors, at what scope of coverage.

This is a rare moment in enterprise security: widespread acknowledgement that the current stack is insufficient, combined with an active hunt for defensive tooling that matches the new threat model. Buyers are looking. The question is what they find.

### Existing Buying Patterns

Enterprises already spend substantially on application security:

- Traditional SAST (Veracode, Checkmarx, Fortify) — mature, entrenched, expensive
- Modern SAST (Semgrep, CodeQL, Snyk Code) — developer-friendly, pattern-based
- DAST (OWASP ZAP, Burp Enterprise, Invicti) — runtime testing
- Dependency scanning (Snyk, Dependabot, Mend) — supply chain
- Secrets scanning (GitGuardian, Gitleaks) — credential leaks
- Runtime protection (Wiz, CrowdStrike, Sysdig) — production defense
- Bug bounty platforms (HackerOne, Bugcrowd) — human researcher access

The platform described in these documents does not replace most of these. It adds a new category: adversarial reasoning-based verification during build, not pattern scanning. Positioning must be clear about what it replaces (little), what it complements (most), and what it adds (capability the rest lack).

---

## The Elephant: Claude Code Security

Any platform built on Claude that focuses on security must address Claude Code Security directly. Customers will ask. The honest answer matters.

### What Claude Code Security Is

Anthropic's Claude Code Security, launched in February 2026, scans codebases for vulnerabilities and proposes patches for human review. It reasons about code rather than pattern-matching, performs adversarial verification on its own findings, and integrates into Claude Code workflows. It is available to Claude Enterprise and Team customers in limited research preview.

### Where It Is Strong

- Directly from Anthropic, with the latest model access
- Deep integration with Claude Code developer workflow
- Adversarial verification on findings
- Trusted brand in AI security discourse
- Lowest marginal cost of Claude model access

### Where There Is Room

Claude Code Security is, by design, a scanner. It inspects existing code. It is not positioned as:

- A platform for secure generation of new websites from a brief
- An end-to-end pipeline covering architecture, implementation, supply chain, and deployment
- A multi-model platform where the Red Team and Blue Team can use different providers
- A workflow orchestrator for security teams coordinating dev and security handoffs
- A compliance evidence generator producing audit-ready artifacts
- A vertically specialized product for web application builders specifically

Claude Code Security is a capability. The platform described in these documents is a workflow product that uses Claude (and possibly other models) as one of its components. The distinction matters to buyers who want outcomes, not tools.

### The Honest Risk

Anthropic may expand Claude Code Security's scope toward workflow orchestration. If they do, a thin wrapper on Claude API is in trouble. The platform must be defensible on dimensions Anthropic is unlikely to prioritize:

- Multi-model support (Anthropic will never be multi-provider)
- Workflow shapes beyond code review (threat modeling, deployment, continuous)
- Deep vertical specialization (e.g., e-commerce, healthcare, fintech)
- Customer-owned evaluation and evidence
- Integration with existing security toolchains buyers already own

Defensibility is a product decision, not a wish. Every roadmap choice either strengthens or weakens it.

---

## Target Customers

The platform is not for everyone. Disciplined segmentation is worth more than broad positioning.

### Segment A: Digital Agencies and Website Builders

Firms that build websites for clients. They face two pressures: clients increasingly ask about security posture, and the agencies' own liability exposure is rising as Mythos-class attacks proliferate. They are unlikely to hire dedicated application security staff at agency scale.

**Why they buy:** Differentiated offering ("we ship Mythos-resistant sites"), reduced post-launch remediation cost, evidence for client security questionnaires.

**Price sensitivity:** Moderate. They pass costs to clients but compete on price.

**Sales motion:** Product-led, with partner-channel expansion through agency networks.

### Segment B: Product Teams at SMB and Mid-Market

In-house teams building customer-facing web applications at companies without dedicated application security programs. They know they should be doing more on security but lack the expertise and tooling budget of larger enterprises.

**Why they buy:** Security that doesn't require hiring security engineers, compliance evidence for SOC 2 and similar, peace of mind.

**Price sensitivity:** High. They are price-comparing with Snyk, Semgrep, and bundled offerings.

**Sales motion:** Self-service with guided onboarding, usage-based pricing.

### Segment C: Platform Engineering Teams

Teams building internal developer platforms at larger companies. They want to bake security into the golden paths developers use, rather than relying on security-team-owned gates.

**Why they buy:** Shift-left that actually shifts (findings arrive while developers still own the code), a story to tell their CISO, integration with their existing platform.

**Price sensitivity:** Moderate. Budgets exist but procurement is slow.

**Sales motion:** Land-and-expand, starting with a single team, with strong integration APIs.

### Segment D: Regulated Industries

Healthcare, fintech, government contractors. They must demonstrate security rigor for compliance, and they are particularly exposed to the post-Mythos threat environment because of the value of their data.

**Why they buy:** Audit evidence, reduced regulatory risk, early adoption of AI-native defenses that regulators will eventually mandate.

**Price sensitivity:** Low for genuine solutions, high for pretenders. Procurement is slow and stringent.

**Sales motion:** Enterprise sales with compliance specialists, dedicated customer success.

### Segment E: Security-Conscious Consumer Brands

Companies whose consumer trust is their brand (financial services, healthcare-adjacent, privacy-focused). A breach is existential. They pay for the best tools available.

**Why they buy:** Reputation protection, competitive differentiation via security posture, board-level risk reduction.

**Price sensitivity:** Low for top-tier solutions.

**Sales motion:** Enterprise sales with technical depth, reference customer emphasis.

### Segments To Deliberately Avoid Initially

- **Large enterprises with mature AppSec programs.** They will demand enterprise features, extensive integrations, and proof at a scale the platform cannot yet provide. They are the wrong early customer.
- **Individual developers and hobbyists.** Unit economics will not work. Freemium at this level cannibalizes paid tiers without converting.
- **Government and defense.** Procurement cycles are too long for a startup's runway. Address later through partners with existing contracts.

---

## Value Proposition

Different segments care about different things. The core value proposition, phrased generically:

> Ship websites that resist the vulnerability classes Mythos-class attackers find — with evidence, not assertions. Our platform runs adversarial AI agents against your code before it ships, produces working proof-of-concept exploits for every issue, applies fixes that are verified against those exploits, and delivers an audit-ready report you can show your customers and regulators.

Segment-adapted framing:

**For agencies:** "Win client pitches by shipping sites that pass the AI-era threat model. Close faster with evidence you can show."

**For mid-market product teams:** "The AppSec program you never hired. Built into your deploy pipeline, priced for your budget."

**For platform engineering:** "Developer-native security that catches what pattern scanners miss. Integrates where your developers already work."

**For regulated industries:** "Defensible evidence of adversarial security verification for every release. Aligned with emerging regulatory expectations for AI-era software."

**For consumer brands:** "The strongest commercially available defense against Mythos-class vulnerability discovery. Because your customers' trust is the asset."

### What Not To Say

- "Provably secure." The platform is not. No platform is.
- "Replaces your security team." It does not. Security teams use it.
- "Catches everything." It does not. Evaluation data is published to demonstrate what it does and does not catch.
- "Cheaper than Snyk." Price competition is a race to zero. Compete on outcomes.

Exaggerated claims are immediately tested in a security context. Credibility lost early is very difficult to recover.

---

## Pricing

Pricing has to match how customers actually buy security tools and how the platform's unit economics work.

### Unit Economics

Each workflow consumes real resources: agent tokens (the largest component), sandbox compute, orchestration overhead, human review cost for premium tiers. A typical full site assessment workflow, at current model prices, costs on the order of $50–$500 in direct costs depending on code size, iteration count, and agent configuration. Continuous monitoring workflows are cheaper per run but run more frequently.

Gross margin target: 65–75% at steady state. Achievable with current model pricing and disciplined budget controls; tighter if customers demand aggressive SLAs.

### Pricing Models Considered

**Per-workflow.** Simple, maps directly to value. Buyers understand it. Works well for agencies and one-off assessments. Bad for continuous monitoring use cases.

**Per-seat subscription.** Familiar SaaS model. Easy to procure. Disconnected from actual usage, which creates abuse (one seat running thousands of workflows) or under-utilization (seats purchased and unused).

**Usage-based (tokens or findings).** Directly tracks resource consumption. Bill of horror for customers who can't predict bills. Not how security teams prefer to buy.

**Tiered subscription with workflow caps.** The standard modern SaaS approach. Starter tier, growth tier, enterprise tier, each with included workflow credits and overage pricing.

**Hybrid: subscription + usage overage.** Base subscription buys a credit pool; overage at clear per-workflow rates. Predictable for buyers, fair to the platform.

### Recommended Pricing Structure

Four tiers:

| Tier | Monthly | Included | Best for |
|------|---------|----------|----------|
| Starter | $299 | 5 full assessments, 25 continuous scans | Small agencies, single-product startups |
| Growth | $1,499 | 30 full assessments, 200 continuous scans | Mid-market product teams, growing agencies |
| Scale | $4,999 | 120 full assessments, unlimited continuous scans, priority support | Platform teams, larger agencies |
| Enterprise | Custom | Unlimited, dedicated instance, compliance features, custom SLAs | Regulated industries, large enterprises |

Overage pricing clearly published for Starter, Growth, and Scale. Enterprise negotiated. Annual contracts offer 15–20% discount on monthly rates.

### What This Pricing Implies

These numbers assume the platform reaches steady-state efficiency at scale. Early-stage pricing for design partners and beta customers will be materially below this, to generate reference stories and iterate on the product. Public pricing should not be set until the platform can actually fulfill at the margins above.

Pricing is a leading signal of positioning. Starter at $299 signals "accessible to small teams." Starter at $2,999 signals "enterprise product." Choose deliberately.

---

## Sales Motion

Different segments need different motions. Trying to run one motion across all segments dilutes both.

### Product-Led Motion (Segments A, B)

Customers discover the platform, sign up themselves, complete an initial workflow within a guided onboarding, and convert to paid based on results. Key requirements:

- Self-service signup with payment on file
- Time-to-first-value under 30 minutes (first workflow completed)
- Transparent pricing visible before signup
- Clear output customers can immediately use (share with clients, drop into compliance docs)
- Usage dashboard showing credit consumption in real time
- Automated upgrade prompts as usage approaches limits

### Sales-Assisted Motion (Segment C)

Platform engineering teams need technical validation before adoption. They evaluate in a shared trial, make a procurement case internally, and deploy to a pilot team before expansion. Key requirements:

- Technical buyer enablement (integration guides, API documentation, architecture whitepapers)
- Free pilot period with success criteria agreed in advance
- Direct access to engineering for integration questions
- Reference customer program
- Expansion playbook from first team to platform-wide

### Enterprise Sales Motion (Segments D, E)

Regulated and high-value customers have procurement processes, security reviews, and legal cycles measured in months. Key requirements:

- Dedicated account executives
- SOC 2 Type 2 certification (non-negotiable)
- Relevant compliance attestations (HIPAA, PCI as applicable)
- Data processing agreements, business associate agreements
- Security questionnaire responses already prepared
- Executive relationships cultivated over time

### Sequencing

Start product-led. Establish unit economics, prove conversion, build public evaluation numbers. Add sales-assisted motion in year two when product maturity and reference customers support it. Add enterprise motion only when compliance posture is ready; enterprise selling before compliance readiness burns trust and pipeline.

---

## Distribution and Partnerships

Direct sales alone limits reach. Several partnership channels are worth considering.

### Integration Partnerships

Deep integrations into the tools developers already use:

- GitHub and GitLab (app marketplaces, Actions integrations)
- Vercel, Netlify, Cloudflare (pre-deploy gate integration)
- Jira, Linear (findings workflow)
- Slack (notifications and approval workflow)
- Cloud providers (AWS, GCP, Azure marketplaces)

These reduce friction for self-service customers and provide distribution surface.

### Agency Channel

Digital agencies can resell or white-label. Revenue share with agencies who bring customers. A meaningful channel if the product quality supports the agency's client relationships.

### Security Consultancy Channel

Boutique security consultancies often want AI-native tooling to multiply their billable work. Partner pricing, training, and co-selling arrangements can produce strong returns if the consultancy network is well-managed.

### Technology Alliances

Partnerships with adjacent security vendors (runtime protection, dependency scanning, CSPM) where integrated offerings are more valuable than individual ones. Reference architectures, joint marketing, mutual customer introductions.

### What Not To Do Early

- Global system integrator partnerships. These burn enormous relationship capital for slow returns. Revisit at scale.
- Exclusive deals with any single platform vendor. Anthropic-exclusivity particularly narrows the market.
- Reseller-only distribution. Losing direct customer relationships means losing product feedback.

---

## Metrics That Matter Commercially

Separate from the evaluation metrics in the preceding document, these business metrics determine whether the company works:

| Metric | Why it matters | Target (steady state) |
|--------|----------------|----------------------|
| New ARR | Growth rate | Varies by stage |
| Gross margin | Unit economics viability | 65–75% |
| Net revenue retention | Expansion proving value | >120% |
| Gross revenue retention | Churn indicator | >90% |
| CAC payback period | Go-to-market efficiency | <18 months |
| Time to first value | Product-led viability | <30 minutes |
| Activation rate | Trial-to-paid indicator | >25% for product-led |
| Magic number | Sales efficiency | >0.75 |
| Rule of 40 | Growth + margin balance | >40 combined |

The metrics that matter most vary by stage. Early: activation rate, time to first value, design-partner testimonials. Middle: NRR, CAC payback, sales efficiency. Late: Rule of 40, market share, category definition.

---

## Phasing

The platform is not shipped in a day. Commercial phasing:

### Phase 0: Design Partners (Months 0–4)

Ten to fifteen hand-selected customers in segments A and B. Free access in exchange for deep feedback and case study rights. Goals: validate the core workflows, produce reference stories, shape pricing based on willingness-to-pay signals.

### Phase 1: Closed Beta (Months 5–8)

Paid pilots with fifty to one hundred customers. Pricing below long-term target but material (no free tier at this stage). Goals: prove unit economics, validate pricing model, build case studies.

### Phase 2: Public Launch (Months 9–12)

Product-led motion opens to self-service for segments A and B. Sales-assisted motion for segment C. Public pricing established. Goals: demonstrate category, build install base, achieve $1M ARR milestone.

### Phase 3: Enterprise Readiness (Year 2)

SOC 2 Type 2, HIPAA, compliance playbooks, enterprise sales team hired. Segment D and E access. Goals: unlock higher ACVs, build moat through compliance investment.

### Phase 4: Category Leadership (Years 3+)

Platform breadth (more workflow shapes, more verticals, more integrations). Strategic partnerships. International expansion. Goals: market leadership in AI-native application security verification.

---

## Risk Register

The commercial risks worth planning for, not wishing away.

### R1: Anthropic expands Claude Code Security

Probability: Medium-High over 18 months. Impact: Severe for any thin-wrapper product, moderate for a defensible workflow platform. Mitigation: invest in multi-model, deep workflow, and vertical specialization. Monitor Anthropic releases; be ready to reposition.

### R2: Open-source alternatives emerge

Probability: High. Open-source projects will attempt the same architecture. Impact: Pricing pressure and commoditization risk. Mitigation: compete on evaluation quality, operational maturity, and workflow depth. Be the easy-to-buy option for teams that don't want to run their own.

### R3: Model capability outpaces positioning

Probability: Medium. If models get much better at code generation with built-in security properties, a "verify after the fact" platform loses value. Mitigation: evolve toward generation-time security, which the blueprint already supports.

### R4: Liability exposure from missed vulnerabilities

Probability: Medium. A customer ships an exploit the platform missed; damages occur; lawyers get called. Mitigation: clear contract language, insurance, honest confidence scoring, evidence-based reporting. Never promise what cannot be delivered.

### R5: Security incident in the platform itself

Probability: Medium-high. A platform that attacks code will be attacked. Impact: catastrophic to brand. Mitigation: the sandboxing and platform-security investments detailed in earlier documents, bug bounty program from day one, transparent incident disclosure when incidents occur.

### R6: Commoditization of AI security tools

Probability: High over 3 years. Every DevSecOps vendor will add AI. Differentiation erodes. Mitigation: defensible workflow, customer relationships, evaluation evidence, and network effects (customers' findings improve evaluation suites).

### R7: Regulatory changes

Probability: Medium. Governments will regulate AI in security contexts. Impact: could be tailwind (mandated evidence-based verification) or headwind (new compliance burdens). Mitigation: active policy engagement, compliance team investment, readiness to adapt.

### R8: Reputation from a public failure

Probability: Medium over 3 years. A customer breach that the platform "should have caught" becomes a news story. Mitigation: conservative confidence scoring, clear scope disclosure, strong public evaluation record, communications plan ready.

---

## Messaging Discipline

Across all channels, a few messaging disciplines pay off:

**Lead with evidence, not claims.** Published evaluation numbers. Reference customer quotes. Specific vulnerability classes detected. Specific patches generated. The market has heard vague "AI-powered security" pitches too many times.

**Acknowledge limitations.** Every piece of public content includes what the platform does not catch. Counter-intuitively, this builds trust faster than universal claims.

**Speak to multiple audiences.** Developers, security teams, and procurement each need different stories. The developer cares about integration. The security team cares about signal quality. Procurement cares about compliance. Respect the difference.

**Avoid fear-based selling.** Mythos is already scary. Leaning into fear looks opportunistic. Lean into capability: here is what you can now do that you could not do before.

**Refuse to overclaim about AI.** The market is saturated with AI hype. Distinguishing the platform requires explaining specifically how AI is used, where it adds value, where traditional tools remain better. Sophistication signals are credibility signals.

---

## The Honest Commercial Assessment

This platform occupies a narrow but real commercial window. The window exists because Mythos-class capabilities are newly public, the defensive tooling market is unprepared, Anthropic's own offering is scoped narrowly, and buyers are actively looking for solutions. The window will close as Anthropic expands Claude Code Security, as open-source alternatives emerge, and as existing vendors integrate AI capabilities into their own stacks.

Success requires three things simultaneously:

1. **Technical execution** at the level described in the preceding documents
2. **Commercial discipline** on segmentation, pricing, and sales motion
3. **Speed** to establish customer relationships and evaluation credibility before the window narrows

Miss any of the three and the platform fails commercially regardless of technical merit.

The plan is defensible, the market is real, and the timing is right — under the condition that execution matches the opportunity. A technically excellent platform with bad commercial decisions dies. A commercially excellent pitch on a weak technical platform dies slower but just as certainly. The bar is both.

---

## Relationship to Earlier Documents

The preceding documents describe what is built. This one describes why anyone pays for it and how it reaches them. Every roadmap decision is a joint technical and commercial decision — a feature prioritized correctly for the buyer in segment C may be wrong for segment A, and investment in compliance (segment D) is investment taken from feature breadth (segment A).

These tensions are productive when surfaced and corrosive when ignored. The platform team should revisit segmentation and positioning at least quarterly; the technical team should participate in those conversations directly.

---

*Document version 1.0 — companion to mythos-defense-platform-blueprint.md, mythos-defense-platform-deep-dive.md, mythos-defense-platform-sandboxing.md, mythos-defense-platform-orchestrator.md, and mythos-defense-platform-evaluation.md*
