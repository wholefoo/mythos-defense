# Mythos Defense Platform

**Autonomous AI-powered web security assessment and hardening CLI.**

Mythos Defense orchestrates multiple AI agents to perform threat modeling, vulnerability scanning, automated patching, and deployment hardening — all from a single command line tool.

---

## Overview

Mythos Defense is a Python CLI platform that uses Claude (Anthropic's AI) to autonomously secure web applications. It implements an adversarial red-team/blue-team loop: scan for vulnerabilities, generate patches, verify fixes, and produce hardened deployment configurations.

The platform supports the full lifecycle from project scaffolding through deployment and continuous monitoring.

## Key Features

- **AI-Powered Threat Modeling** — STRIDE-based analysis generates attack trees and prioritized threat assessments
- **Automated Vulnerability Scanning** — Pluggable adapter system (Semgrep, mock fixtures) identifies security issues
- **Autonomous Patching** — Blue Team agent generates unified diffs with regression tests for each finding
- **Supply Chain Auditing** — SBOM generation and dependency vulnerability analysis (npm audit, pip-audit, CycloneDX)
- **Deployment Hardening** — Produces TLS, CSP, CORS, and rate-limiting configurations
- **Continuous Monitoring** — Scheduled re-scans with webhook notifications and auto-fix capabilities
- **Multi-Platform Deployment** — Comparison matrix and deploy support for Vercel, Netlify, AWS, Modal, GitHub Pages
- **AI-Generated Reports** — Weekly security posture reports with executive summaries

## Installation

Requires Python 3.11+.

```bash
pip install .
```

Or install in development mode:

```bash
pip install -e ".[dev]"
```

## Configuration

1. Set your Anthropic API key:

```bash
# .env file in your project root
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
```

2. (Optional) Install Semgrep for real vulnerability scanning:

```bash
pip install semgrep
```

## Commands

### Core Security Commands

| Command | Description |
|---------|-------------|
| `mythos assess` | Run a full security assessment workflow (scan, patch, verify loop) |
| `mythos threat-model` | Generate a STRIDE threat model from a project brief |
| `mythos harden` | Run red-team/blue-team adversarial hardening iterations |
| `mythos audit` | Generate SBOM and audit dependencies for vulnerabilities |
| `mythos doctor` | Verify that all tools and adapters are configured correctly |

### Project Lifecycle Commands

| Command | Description |
|---------|-------------|
| `mythos init` | Bootstrap a workspace with directories, keys, and MCP integrations |
| `mythos new` | Scaffold a new Next.js/Tailwind/Shadcn project |
| `mythos plan` | AI-powered planning with quality bar validation |
| `mythos build` | Autonomous code generation from a plan using AI agents |
| `mythos review` | Screenshot-based visual QA with Claude vision + auto-fix |

### Operations Commands

| Command | Description |
|---------|-------------|
| `mythos sandbox up/down/smoke/status` | Manage isolated dev server environments |
| `mythos deploy` | Deploy or compare hosting platforms (Vercel, Netlify, AWS, etc.) |
| `mythos watch` | Continuous security monitoring with configurable scan intervals |
| `mythos report` | Generate weekly security and performance reports |

## Usage Examples

### Run a Security Assessment

```bash
mythos assess -w ./my-project -b project_brief.md -a semgrep
```

This will:
1. Generate a threat model from your project brief
2. Scan the codebase for vulnerabilities
3. Automatically generate patches for each finding
4. Verify patches don't break existing functionality
5. Analyze supply chain dependencies
6. Produce deployment hardening recommendations
7. Output a full report to `./workflows/`

### Generate a Threat Model

```bash
mythos threat-model -b project_brief.md
```

Outputs a STRIDE-based threat model with attack vectors, impact ratings, and recommended mitigations.

### Continuous Monitoring

```bash
mythos watch -w ./my-project -i 3600 --auto-fix --notify https://hooks.slack.com/...
```

Scans every hour, auto-patches new findings, and sends alerts to your webhook.

### Compare Deployment Platforms

```bash
mythos deploy --compare vercel,netlify,aws --show cost,features,latency,ai-fit
```

### Deploy to Production

```bash
mythos deploy -w ./my-project --target vercel
```

### Full Pipeline Example

```bash
mythos init -d ./new-project
mythos new -w ./new-project --name my-saas-app
mythos plan -w ./new-project -b "SaaS dashboard with auth and billing"
mythos build -w ./new-project
mythos review -w ./new-project
mythos harden -w ./new-project
mythos audit -w ./new-project
mythos sandbox up -w ./new-project
mythos sandbox smoke -w ./new-project
mythos deploy -w ./new-project --target vercel
mythos watch -w ./new-project -i 3600 --auto-fix
```

## Architecture

```
mythos-defense/
├── src/mythos_defense/
│   ├── cli.py                 # Main CLI entry point
│   ├── commands/              # All 10 pipeline commands
│   ├── agents/                # AI agents (Architect, Blue Team, Supply Chain, Deployment)
│   ├── adapters/              # Red Team adapters (Semgrep, Mock)
│   ├── orchestrator/          # Workflow engine, budget tracking, patch verification
│   ├── schemas/               # Pydantic models (Finding, FindingSet)
│   └── prompts/               # Agent system prompts (Markdown)
├── tests/                     # Test suite with fixtures
├── docs/                      # Platform documentation
└── pyproject.toml             # Package configuration
```

### Agent System

| Agent | Model | Role |
|-------|-------|------|
| Architect | claude-opus-4-7 | Threat modeling, attack surface analysis |
| Blue Team | claude-sonnet-4-6 | Patch generation with regression tests |
| Supply Chain | claude-sonnet-4-6 | Dependency risk assessment |
| Deployment | claude-sonnet-4-6 | Infrastructure hardening configs |

### Red Team Adapters

- **Semgrep** — Static analysis with 2000+ community rules
- **Mock** — Replay JSON fixtures for testing and development

### Orchestrator Loop

```
Architect (threat model)
    → Red Team (scan for vulnerabilities)
        → Blue Team (generate patches)
            → Verify (apply + test patches)
                → Supply Chain (audit dependencies)
                    → Deployment (harden config)
                        → Report
```

Budget enforcement ensures the loop terminates within configured limits (max iterations, max tokens, per-finding attempt caps).

## Use Cases

- **Startup Security** — Get enterprise-grade security assessment without a dedicated security team
- **CI/CD Integration** — Run `mythos assess` in your pipeline to catch vulnerabilities before deploy
- **Compliance Preparation** — Generate threat models and audit reports for SOC2/ISO27001 evidence
- **Dependency Monitoring** — Continuous SBOM generation and vulnerability tracking
- **Greenfield Projects** — Scaffold, build, and harden new apps from a single tool
- **Incident Response** — Quickly identify and patch vulnerabilities when they're disclosed

## Requirements

- Python 3.11+
- Anthropic API key (Claude access)
- Optional: Semgrep (for real scanning), Node.js (for project scaffolding/deploy), Playwright (for visual review)

## License

MIT

## Contributing

1. Fork the repository
2. Create a feature branch
3. Install dev dependencies: `pip install -e ".[dev]"`
4. Run tests: `pytest`
5. Submit a pull request
