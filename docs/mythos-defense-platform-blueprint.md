# Agentic Workflow Platform for Exploit-Resistant Website Design

**A Blueprint for Defending Against Mythos-Class Vulnerabilities**

---

## Overview

This document outlines the architecture and build plan for an agentic workflow platform that designs websites hardened against the vulnerability classes exposed by Anthropic's Claude Mythos Preview model. The platform uses specialized AI agents in an adversarial pipeline to produce websites with dramatically reduced attack surface.

---

## Core Design Principle

The central insight from Mythos is that **reasoning-based adversarial verification works** — and works both offensively and defensively. This platform weaponizes this insight for defense by running adversarial agents against every artifact before it ships.

Anthropic's own red team scaffold was simple: isolated container + Claude Code + "find a vulnerability" prompt + let it experiment. This platform industrializes that pattern into a repeatable, auditable workflow.

---

## Target Vulnerability Classes

Based on Mythos's findings, the web-specific vulnerability categories to defend against:

- **Authentication/authorization bypasses** — logic flaws in session, JWT, OAuth flows
- **Injection attacks** — SQLi, XSS, SSTI, command injection, prototype pollution
- **Broken access control** — IDOR, missing authorization checks, privilege escalation
- **Cryptographic implementation flaws** — weak randomness, JWT algorithm confusion, bad TLS config
- **Race conditions** — TOCTOU issues in payment, inventory, and auth flows
- **API logic flaws** — identified as the dominant enterprise attack surface
- **Supply chain vulnerabilities** — dependency vulnerabilities, typosquatting, malicious packages
- **Configuration errors** — exposed secrets, permissive CORS, missing security headers

---

## Agent Architecture

Six specialized agents orchestrated by a central coordinator:

### 1. Architect Agent
- Threat-models the design **before** any code is written
- Produces a STRIDE-style threat model
- Generates a security requirements document
- Defines trust boundaries and data flow diagrams

### 2. Implementation Agent
- Generates code with security requirements injected into the system prompt
- Enforces parameterized queries, output encoding, authorization checks on every endpoint
- Follows secure-by-default patterns for the chosen framework

### 3. Red Team Agent
- Adversarial agent that actually attempts to exploit the code in a sandbox
- Not just static analysis — runs the app and attacks it
- Produces working proofs-of-concept, not theoretical flaws
- This is the core Mythos-inspired pattern

### 4. Blue Team Agent
- Reviews Red Team findings
- Proposes patches
- Verifies patches close the issue without introducing regressions

### 5. Supply Chain Agent
- Audits dependencies
- Generates SBOM (Software Bill of Materials)
- Checks against CVE databases
- Detects typosquats and malicious packages

### 6. Deployment Agent
- Hardens infrastructure configuration
- Sets TLS, CSP, security headers
- Manages secrets
- Configures IAM policies

---

## Pipeline Architecture

```
Intake → Threat Model → Architecture → Implementation 
   ↓
Adversarial Test Loop (Red ↔ Blue) ← ← ← 
   ↓                                     ↑
Supply Chain Audit → Deployment Hardening ↑
   ↓                                     ↑
Findings Report → Human Approval Gate ───↑ (if issues)
   ↓
Deploy → Continuous Monitoring
```

The Red/Blue adversarial loop is the core mechanism. Iteration continues until the Red Team Agent cannot find exploits within N rounds, or until a defined confidence threshold is reached.

---

## Technology Stack

### Orchestration
- **Temporal** or **LangGraph** for durable, stateful agent workflows

### Models
- **Claude Opus 4.7** — Architect and Red Team agents (hard reasoning tasks)
- **Claude Sonnet 4.6** — Implementation and Blue Team agents (throughput)
- **Claude Haiku 4.5** — Classification and triage (fast, cheap)

### Agent Runtime
- **Claude Code SDK** for code-touching agents
- **Anthropic API with tool use** for all other agents

### Sandboxing
- **Firecracker microVMs** or **gVisor containers**
- Strict isolation — the Red Team Agent must never touch anything outside the sandbox

### Deterministic Security Tools (wrapped as agent-callable tools)
- **Semgrep** — pattern-based SAST
- **CodeQL** — semantic code analysis
- **Snyk** — dependency scanning
- **OWASP ZAP** — dynamic application security testing
- **nuclei** — vulnerability scanner
- **trivy** — container and IaC scanning
- **npm audit** — Node dependency audit
- **gitleaks** — secret detection

### Storage
- **PostgreSQL** — findings database and audit log
- **S3-compatible object storage** — artifacts, reports, SBOMs

### Frontend
- Framework-agnostic dashboard over the pipeline
- Provides findings review, approval workflows, and reporting

---

## Critical Guardrails

These are non-negotiable requirements:

### Human Approval Gates
- Required at architecture sign-off
- Required before deployment
- No automated merges of security-critical changes

### Scope Enforcement
- Agents can only test systems the user explicitly owns
- Prompt-injection guards on all user input
- Strict authorization checks before any tool execution

### Cost Controls
- Hard budget per workflow
- Maximum iteration count per adversarial loop
- Timeout on every agent turn

### Comprehensive Audit Logging
- Every prompt recorded
- Every tool call logged
- Every finding timestamped and attributed
- Immutable append-only log

### Defense of the Platform Itself
- The platform is a target — treat it accordingly
- Remember: Check Point found RCE in Claude Code via malicious `.claude/settings.json` files
- Assume the platform will be attacked the same way
- Red-team your red-teamer

### Prompt Injection Defense
- When the Red Team Agent reads user-supplied code or data, that content can attempt to hijack the agent
- Sandbox all untrusted content
- Use structured tool outputs
- Never allow agents to execute arbitrary commands outside the sandbox

---

## Build Phases

### Phase 1: MVP (4–6 weeks)
- Single-repo scanner
- Architect + Red Team + Blue Team agents only
- Target a single framework (e.g., Next.js)
- Validate the adversarial loop end-to-end on deliberately vulnerable apps (Juice Shop, DVWA)
- Goal: prove the core loop works

### Phase 2: V1 (2–3 months)
- Add Implementation Agent for full website generation
- Add Supply Chain Agent
- Integrate all deterministic security tools
- Build persistent findings database and dashboard
- Goal: complete end-to-end website creation with security verification

### Phase 3: V2
- Add Deployment Agent with IaC generation (Terraform, Pulumi)
- Continuous monitoring capabilities
- Integration with real deployment targets (Vercel, Netlify, AWS)
- Goal: production-ready deployment pipeline

### Phase 4: V3
- Multi-tenant SaaS architecture
- Custom agent configurations per organization
- Compliance reporting (SOC 2, PCI mappings)
- Goal: enterprise-ready platform

---

## Honest Limitations

These must be acknowledged in product positioning:

- Even Mythos-class models miss vulnerabilities
- AISLE research showed the capability frontier is jagged — no single model dominates across all tasks
- The platform produces **evidence**, not **guarantees**
- Correct positioning: "dramatically reduces the vulnerability surface that Mythos-class attackers will find"
- Incorrect positioning: "provably secure"

Many findings from AI security tools are unexploitable in production due to defense-in-depth (ASLR, SELinux, WAFs). The Red Team Agent should produce working proofs-of-concept, not theoretical flaws. This keeps signal-to-noise high and maintains user trust.

---

## Success Metrics

Track these to validate the platform is working:

- **Exploit discovery rate** — vulnerabilities found per codebase
- **False positive rate** — percentage of findings that are not genuinely exploitable
- **Time to patch** — from discovery to verified fix
- **Regression rate** — patches that introduce new vulnerabilities
- **Cost per workflow** — total API and infrastructure cost per website
- **Human review burden** — hours of human time per deployment

---

## Reference Material

Key sources informing this blueprint:

- Anthropic's Mythos Preview technical report (red.anthropic.com)
- Project Glasswing announcement
- Anthropic Claude Code Security (limited research preview)
- Check Point Research disclosures on Claude Code vulnerabilities (CVE-2025-59536, CVE-2026-21852)
- Wiz, Corelight, and Red Hat analyses of the post-Mythos security landscape
- AISLE's "jagged frontier" research on AI cybersecurity capabilities

---

*Document version 1.0*
