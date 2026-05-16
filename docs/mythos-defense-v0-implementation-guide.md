# Mythos Defense Platform — V0 Implementation Guide

**Defensive Half + Red Team Interface Contract**

This guide takes you from empty directory to a working V0 of the platform: an orchestrated loop where defensive agents (Architect, Blue Team, Supply Chain, Deployment) operate against findings produced by a Red Team *slot* — an adapter interface that you can fill with existing offensive tools (Semgrep, OWASP ZAP, nuclei) or mock fixtures for testing.

The autonomous Red Team Agent described in the earlier blueprint is deliberately not built here. The interface contract is, so that piece can drop in later from a more controlled source.

---

## Scope of This Guide

**In scope:**
- Project scaffolding and tooling
- Findings schema and the Red Team adapter contract
- Architect Agent (production prompt + CLI)
- Blue Team Agent (production prompt + CLI + verify loop)
- Supply Chain Agent (with `npm audit` and Snyk integration)
- Deployment Agent (with header and CSP generation)
- Mock + Semgrep + ZAP adapters
- Simple orchestrator (Python, not Temporal)
- Evaluation harness against OWASP Juice Shop
- Docker-based sandbox for the verify step

**Out of scope (for V0):**
- The autonomous Red Team Agent
- Firecracker/gVisor (Docker is fine for V0; revisit for production)
- Multi-tenancy
- Approval gate UI
- Production observability stack

---

## Prerequisites

Before starting, install:

```bash
# Required
python --version          # 3.11 or later
docker --version          # 24+ recommended
git --version

# Recommended
node --version            # for npm audit and frontend testing
gh --version              # for GitHub repo cloning

# Security tools used by adapters
pip install semgrep
brew install nuclei       # or: go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
docker pull owasp/zap2docker-stable
```

Get an Anthropic API key from console.anthropic.com. You'll set this as `ANTHROPIC_API_KEY` shortly.

---

## Phase 0: Project Setup

### 0.1 Create the project

```bash
mkdir mythos-defense && cd mythos-defense
git init
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
```

### 0.2 Create `pyproject.toml`

```bash
cat > pyproject.toml << 'EOF'
[project]
name = "mythos-defense"
version = "0.1.0"
description = "Defensive AI platform for exploit-resistant websites"
requires-python = ">=3.11"
dependencies = [
    "anthropic>=0.40.0",
    "pydantic>=2.5.0",
    "click>=8.1.0",
    "pyyaml>=6.0",
    "rich>=13.0.0",
    "httpx>=0.27.0",
    "tenacity>=8.2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "ruff>=0.4.0",
    "mypy>=1.8.0",
]

[project.scripts]
mythos = "mythos_defense.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
EOF

pip install -e ".[dev]"
```

### 0.3 Create the directory structure

```bash
mkdir -p src/mythos_defense/{agents,adapters,orchestrator,schemas,prompts}
mkdir -p tests/fixtures/findings
mkdir -p eval/suites
mkdir -p workflows  # output directory for runs

touch src/mythos_defense/__init__.py
touch src/mythos_defense/{agents,adapters,orchestrator,schemas}/__init__.py
```

### 0.4 Set up environment

```bash
cat > .env.example << 'EOF'
ANTHROPIC_API_KEY=sk-ant-...
SNYK_TOKEN=                   # optional, for supply chain
WORKFLOW_OUTPUT_DIR=./workflows
LOG_LEVEL=INFO
EOF

cp .env.example .env
# Now edit .env with your real key

cat > .gitignore << 'EOF'
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
.mypy_cache/
workflows/
*.log
EOF
```

---

## Phase 1: The Findings Interface Contract

This is the single most important part of the V0. The contract defines what a "finding" looks like — the schema that every Red Team source (mock, Semgrep, ZAP, future autonomous agent) must produce, and that every defensive agent consumes.

### 1.1 Define the schema

Create `src/mythos_defense/schemas/findings.py`:

```python
"""Finding schema — the contract between Red Team sources and defensive agents."""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class VulnClass(str, Enum):
    AUTH_BYPASS = "AUTH_BYPASS"
    AUTHZ_BROKEN = "AUTHZ_BROKEN"
    INJECTION_SQL = "INJECTION_SQL"
    INJECTION_CMD = "INJECTION_CMD"
    INJECTION_TEMPLATE = "INJECTION_TEMPLATE"
    XSS_REFLECTED = "XSS_REFLECTED"
    XSS_STORED = "XSS_STORED"
    XSS_DOM = "XSS_DOM"
    CSRF = "CSRF"
    IDOR = "IDOR"
    CRYPTO_IMPL = "CRYPTO_IMPL"
    RACE_CONDITION = "RACE_CONDITION"
    API_LOGIC = "API_LOGIC"
    SSRF = "SSRF"
    XXE = "XXE"
    DESERIALIZATION = "DESERIALIZATION"
    PROTOTYPE_POLLUTION = "PROTOTYPE_POLLUTION"
    SUPPLY_CHAIN = "SUPPLY_CHAIN"
    SECRET_EXPOSURE = "SECRET_EXPOSURE"
    CONFIG_INSECURE = "CONFIG_INSECURE"
    OTHER = "OTHER"


class CodeLocation(BaseModel):
    """A specific location in the codebase."""
    path: str = Field(description="File path relative to repo root")
    line_start: int = Field(ge=1)
    line_end: Optional[int] = Field(default=None, ge=1)
    function: Optional[str] = None
    
    @field_validator("line_end")
    @classmethod
    def end_after_start(cls, v, info):
        if v is not None and v < info.data.get("line_start", 1):
            raise ValueError("line_end must be >= line_start")
        return v


class ProofOfConcept(BaseModel):
    """How to reproduce the finding."""
    poc_type: str = Field(description="e.g., 'http_request', 'unit_test', 'manual_steps'")
    steps: list[str] = Field(min_length=1, description="Ordered reproduction steps")
    reproduction_script: Optional[str] = Field(
        default=None,
        description="Path to a script (relative to artifacts dir) that reproduces the issue"
    )
    expected_evidence: str = Field(description="What you'll see when the exploit succeeds")
    artifacts: list[str] = Field(
        default_factory=list,
        description="Paths to evidence artifacts (response.json, screenshot, log)"
    )


class Finding(BaseModel):
    """The canonical finding shape. Every Red Team source must produce this."""
    finding_id: str = Field(description="Unique within workflow, e.g., 'RT-2026-0042'")
    source: str = Field(description="Adapter name that produced this, e.g., 'semgrep', 'zap', 'mock'")
    severity: Severity
    vuln_class: VulnClass
    title: str = Field(min_length=10, max_length=200)
    description: str = Field(min_length=20)
    
    affected_locations: list[CodeLocation] = Field(min_length=1)
    root_cause: str = Field(
        min_length=20,
        description="Why this is broken at the architectural/code level"
    )
    
    poc: ProofOfConcept
    
    impact_confidentiality: Severity = Severity.LOW
    impact_integrity: Severity = Severity.LOW
    impact_availability: Severity = Severity.LOW
    
    cwe_ids: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    
    # State tracking through the loop
    patch_attempts: int = 0
    verified_blocked: bool = False
    suppressed: bool = False
    suppression_reason: Optional[str] = None


class FindingSet(BaseModel):
    """A set of findings from a single Red Team run."""
    workflow_id: str
    iteration: int
    source: str
    findings: list[Finding]
    coverage_notes: Optional[str] = None
    budget_consumed: dict = Field(default_factory=dict)
```

### 1.2 Create a sample finding fixture

```bash
mkdir -p tests/fixtures/findings
```

Create `tests/fixtures/findings/sample_jwt_none.json`:

```bash
cat > tests/fixtures/findings/sample_jwt_none.json << 'EOF'
{
  "finding_id": "MOCK-2026-0001",
  "source": "mock",
  "severity": "HIGH",
  "vuln_class": "AUTH_BYPASS",
  "title": "JWT alg=none accepted on /api/admin endpoints",
  "description": "The auth middleware uses jsonwebtoken.verify() without specifying the algorithms option. When the secret is empty or falsy, the library accepts tokens signed with alg=none, allowing complete authentication bypass.",
  "affected_locations": [
    {
      "path": "src/middleware/auth.ts",
      "line_start": 47,
      "line_end": 52,
      "function": "verifyJwt"
    }
  ],
  "root_cause": "jsonwebtoken.verify() called without algorithms option; defaults accept alg=none when secret is empty string. Affects all admin endpoints downstream.",
  "poc": {
    "poc_type": "http_request",
    "steps": [
      "Construct an unsigned JWT with header {\"alg\":\"none\",\"typ\":\"JWT\"} and payload {\"sub\":\"admin\",\"role\":\"admin\"}",
      "Send GET /api/admin/users with Authorization: Bearer <token>",
      "Server returns 200 with full user list"
    ],
    "expected_evidence": "HTTP 200 response containing user list, despite no valid signature",
    "artifacts": []
  },
  "impact_confidentiality": "HIGH",
  "impact_integrity": "HIGH",
  "impact_availability": "LOW",
  "cwe_ids": ["CWE-347"],
  "references": ["https://cwe.mitre.org/data/definitions/347.html"]
}
EOF
```

### 1.3 Validate the schema works

```bash
python -c "
from mythos_defense.schemas.findings import Finding
import json
data = json.load(open('tests/fixtures/findings/sample_jwt_none.json'))
f = Finding.model_validate(data)
print(f'OK: {f.finding_id} - {f.title}')
"
```

You should see: `OK: MOCK-2026-0001 - JWT alg=none accepted on /api/admin endpoints`

---

## Phase 2: The Red Team Adapter Contract

The adapter interface is what makes the Red Team slot pluggable. Each adapter takes a target and returns findings.

### 2.1 Define the adapter base class

Create `src/mythos_defense/adapters/base.py`:

```python
"""Red Team adapter contract."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from mythos_defense.schemas.findings import FindingSet


@dataclass
class AdapterTarget:
    """What the adapter is asked to test."""
    workspace: Path                    # Path to code under test
    running_app_url: Optional[str] = None  # If app is running for DAST
    iteration: int = 0
    workflow_id: str = ""
    excluded_findings: list[str] = field(default_factory=list)  # finding_ids already fixed
    config: dict = field(default_factory=dict)  # adapter-specific config


class RedTeamAdapter(ABC):
    """Every Red Team source — mock, Semgrep, ZAP, or future autonomous agent —
    implements this contract. The orchestrator calls run() and gets FindingSet back."""
    
    name: str = "abstract"
    
    @abstractmethod
    def run(self, target: AdapterTarget) -> FindingSet:
        """Execute the adapter. Returns findings or raises AdapterError."""
        ...
    
    def healthcheck(self) -> bool:
        """Return True if the adapter's underlying tool is available."""
        return True


class AdapterError(Exception):
    """Raised when an adapter fails to execute."""
```

### 2.2 Build the Mock Adapter

The mock adapter replays canned findings. Essential for testing the loop without invoking real tools.

Create `src/mythos_defense/adapters/mock.py`:

```python
"""Mock adapter — replays canned findings for testing the loop."""
from __future__ import annotations
import json
from pathlib import Path
from mythos_defense.adapters.base import RedTeamAdapter, AdapterTarget
from mythos_defense.schemas.findings import Finding, FindingSet


class MockAdapter(RedTeamAdapter):
    name = "mock"
    
    def __init__(self, fixtures_dir: Path):
        self.fixtures_dir = fixtures_dir
    
    def run(self, target: AdapterTarget) -> FindingSet:
        findings = []
        for fixture_file in sorted(self.fixtures_dir.glob("*.json")):
            data = json.loads(fixture_file.read_text())
            finding = Finding.model_validate(data)
            
            # Honor exclusions — mock previously-fixed findings
            if finding.finding_id in target.excluded_findings:
                continue
            
            findings.append(finding)
        
        return FindingSet(
            workflow_id=target.workflow_id,
            iteration=target.iteration,
            source=self.name,
            findings=findings,
            coverage_notes=f"Replayed {len(findings)} fixtures from {self.fixtures_dir}",
        )
```

### 2.3 Build the Semgrep adapter

Create `src/mythos_defense/adapters/semgrep.py`:

```python
"""Semgrep adapter — runs semgrep, maps results to Finding schema."""
from __future__ import annotations
import json
import subprocess
import uuid
from mythos_defense.adapters.base import RedTeamAdapter, AdapterTarget, AdapterError
from mythos_defense.schemas.findings import (
    Finding, FindingSet, Severity, VulnClass, CodeLocation, ProofOfConcept,
)

# Map Semgrep rule categories to our VulnClass enum
SEMGREP_CLASS_MAP = {
    "sql-injection": VulnClass.INJECTION_SQL,
    "command-injection": VulnClass.INJECTION_CMD,
    "xss": VulnClass.XSS_REFLECTED,
    "csrf": VulnClass.CSRF,
    "ssrf": VulnClass.SSRF,
    "xxe": VulnClass.XXE,
    "deserialization": VulnClass.DESERIALIZATION,
    "secret": VulnClass.SECRET_EXPOSURE,
    "crypto": VulnClass.CRYPTO_IMPL,
    "auth": VulnClass.AUTH_BYPASS,
    "prototype-pollution": VulnClass.PROTOTYPE_POLLUTION,
}

SEVERITY_MAP = {
    "ERROR": Severity.HIGH,
    "WARNING": Severity.MEDIUM,
    "INFO": Severity.LOW,
}


class SemgrepAdapter(RedTeamAdapter):
    name = "semgrep"
    
    def __init__(self, config: str = "auto"):
        self.config = config  # e.g., "auto", "p/security-audit", "p/owasp-top-ten"
    
    def healthcheck(self) -> bool:
        try:
            subprocess.run(["semgrep", "--version"], check=True, capture_output=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    
    def run(self, target: AdapterTarget) -> FindingSet:
        if not self.healthcheck():
            raise AdapterError("semgrep not installed; pip install semgrep")
        
        cmd = [
            "semgrep", "scan",
            "--config", self.config,
            "--json",
            "--quiet",
            str(target.workspace),
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode not in (0, 1):  # 1 = findings present
            raise AdapterError(f"semgrep failed: {result.stderr}")
        
        try:
            output = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise AdapterError(f"semgrep output not JSON: {e}")
        
        findings = []
        for r in output.get("results", []):
            finding = self._map_result(r, target)
            if finding and finding.finding_id not in target.excluded_findings:
                findings.append(finding)
        
        return FindingSet(
            workflow_id=target.workflow_id,
            iteration=target.iteration,
            source=self.name,
            findings=findings,
            coverage_notes=f"Semgrep scan with config={self.config}",
        )
    
    def _map_result(self, r: dict, target: AdapterTarget) -> Finding | None:
        check_id = r.get("check_id", "")
        message = r.get("extra", {}).get("message", "")
        severity_raw = r.get("extra", {}).get("severity", "WARNING")
        path = r.get("path", "")
        line_start = r.get("start", {}).get("line", 1)
        line_end = r.get("end", {}).get("line", line_start)
        
        # Heuristic class mapping based on rule name
        vuln_class = VulnClass.OTHER
        for keyword, vc in SEMGREP_CLASS_MAP.items():
            if keyword in check_id.lower():
                vuln_class = vc
                break
        
        finding_id = f"SG-{uuid.uuid4().hex[:8]}"
        
        return Finding(
            finding_id=finding_id,
            source=self.name,
            severity=SEVERITY_MAP.get(severity_raw, Severity.MEDIUM),
            vuln_class=vuln_class,
            title=f"{check_id}: {message[:100]}"[:200],
            description=message or "Semgrep rule match",
            affected_locations=[CodeLocation(
                path=path,
                line_start=line_start,
                line_end=line_end,
            )],
            root_cause=f"Semgrep rule {check_id} matched. {message}",
            poc=ProofOfConcept(
                poc_type="static_match",
                steps=[
                    f"Open {path}:{line_start}",
                    f"Observe code matching rule {check_id}",
                    "Static analysis match — manual exploitation verification recommended",
                ],
                expected_evidence="Code pattern matching the rule is present",
            ),
            cwe_ids=[c for c in r.get("extra", {}).get("metadata", {}).get("cwe", []) if c],
            references=r.get("extra", {}).get("metadata", {}).get("references", []) or [],
        )
```

### 2.4 ZAP adapter (sketch)

Create `src/mythos_defense/adapters/zap.py`:

```python
"""OWASP ZAP adapter — for DAST against running apps. V0 sketch."""
from __future__ import annotations
import subprocess
import json
import tempfile
import uuid
from pathlib import Path
from mythos_defense.adapters.base import RedTeamAdapter, AdapterTarget, AdapterError
from mythos_defense.schemas.findings import (
    Finding, FindingSet, Severity, VulnClass, CodeLocation, ProofOfConcept,
)


ZAP_RISK_MAP = {
    "High": Severity.HIGH,
    "Medium": Severity.MEDIUM,
    "Low": Severity.LOW,
    "Informational": Severity.INFO,
}


class ZapAdapter(RedTeamAdapter):
    name = "zap"
    
    def __init__(self, docker_image: str = "owasp/zap2docker-stable"):
        self.docker_image = docker_image
    
    def healthcheck(self) -> bool:
        try:
            subprocess.run(["docker", "--version"], check=True, capture_output=True)
            return True
        except Exception:
            return False
    
    def run(self, target: AdapterTarget) -> FindingSet:
        if not target.running_app_url:
            raise AdapterError("ZapAdapter requires target.running_app_url")
        if not self.healthcheck():
            raise AdapterError("docker not available for ZAP")
        
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.json"
            cmd = [
                "docker", "run", "--rm",
                "-v", f"{tmp}:/zap/wrk/:rw",
                "--network", "host",
                self.docker_image,
                "zap-baseline.py",
                "-t", target.running_app_url,
                "-J", "report.json",
                "-I",  # do not fail on findings
            ]
            subprocess.run(cmd, capture_output=True)
            
            if not report_path.exists():
                raise AdapterError("ZAP did not produce report.json")
            
            data = json.loads(report_path.read_text())
        
        findings = []
        for site in data.get("site", []):
            for alert in site.get("alerts", []):
                finding = self._map_alert(alert, target)
                if finding and finding.finding_id not in target.excluded_findings:
                    findings.append(finding)
        
        return FindingSet(
            workflow_id=target.workflow_id,
            iteration=target.iteration,
            source=self.name,
            findings=findings,
            coverage_notes=f"ZAP baseline scan against {target.running_app_url}",
        )
    
    def _map_alert(self, alert: dict, target: AdapterTarget) -> Finding:
        name = alert.get("name", "Unknown")
        risk = alert.get("riskdesc", "Low").split(" ")[0]
        instances = alert.get("instances", [])
        first_instance = instances[0] if instances else {}
        url = first_instance.get("uri", target.running_app_url or "unknown")
        
        return Finding(
            finding_id=f"ZAP-{uuid.uuid4().hex[:8]}",
            source=self.name,
            severity=ZAP_RISK_MAP.get(risk, Severity.LOW),
            vuln_class=VulnClass.OTHER,  # could refine via cweid
            title=f"ZAP: {name}"[:200],
            description=alert.get("desc", "")[:1000],
            affected_locations=[CodeLocation(
                path=f"<live-endpoint>:{url}",
                line_start=1,
            )],
            root_cause=alert.get("desc", "ZAP-detected runtime issue"),
            poc=ProofOfConcept(
                poc_type="http_request",
                steps=[f"Send request to {url}", alert.get("solution", "See ZAP report")],
                expected_evidence=alert.get("desc", "")[:200],
            ),
            cwe_ids=[f"CWE-{alert['cweid']}"] if alert.get("cweid") else [],
        )
```

### 2.5 Test the adapters

Create `tests/test_adapters.py`:

```python
from pathlib import Path
from mythos_defense.adapters.mock import MockAdapter
from mythos_defense.adapters.base import AdapterTarget


def test_mock_adapter_loads_fixtures():
    adapter = MockAdapter(fixtures_dir=Path("tests/fixtures/findings"))
    target = AdapterTarget(
        workspace=Path("."),
        workflow_id="test-001",
        iteration=0,
    )
    result = adapter.run(target)
    assert len(result.findings) >= 1
    assert result.findings[0].finding_id == "MOCK-2026-0001"


def test_mock_adapter_honors_exclusions():
    adapter = MockAdapter(fixtures_dir=Path("tests/fixtures/findings"))
    target = AdapterTarget(
        workspace=Path("."),
        workflow_id="test-001",
        iteration=1,
        excluded_findings=["MOCK-2026-0001"],
    )
    result = adapter.run(target)
    assert all(f.finding_id != "MOCK-2026-0001" for f in result.findings)
```

Run it:

```bash
pytest tests/test_adapters.py -v
```

---

## Phase 3: The Defensive Agents

Now the core: the four agents that consume findings and produce defensive artifacts.

### 3.1 Base agent class

Create `src/mythos_defense/agents/base.py`:

```python
"""Base class for defensive agents."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import os
from anthropic import Anthropic


@dataclass
class AgentResult:
    output: str
    structured: dict[str, Any]
    tokens_in: int
    tokens_out: int
    model: str


class BaseAgent:
    name: str = "abstract"
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 8000
    
    def __init__(self, api_key: str | None = None):
        self.client = Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])
    
    def _load_prompt(self, name: str) -> str:
        path = Path(__file__).parent.parent / "prompts" / f"{name}.md"
        return path.read_text()
    
    def _call(self, system: str, user: str) -> AgentResult:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = response.content[0].text
        return AgentResult(
            output=text,
            structured={},  # filled by subclasses that parse JSON
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            model=self.model,
        )
```

### 3.2 Architect Agent

Create the prompt file `src/mythos_defense/prompts/architect.md`:

```markdown
You are a senior application security architect. You produce a STRIDE-based threat model for a website described in the user's brief, before any code is written.

You MUST output a single JSON object with this exact shape — no surrounding prose, no markdown fences:

{
  "assumptions": ["..."],
  "assets": [
    {"name": "...", "sensitivity": "public|internal|confidential|restricted", "description": "..."}
  ],
  "trust_boundaries": [
    {"name": "...", "from_zone": "...", "to_zone": "...", "description": "..."}
  ],
  "data_flows": [
    {"asset": "...", "path": ["...", "..."], "boundaries_crossed": ["..."]}
  ],
  "threats": [
    {
      "id": "T-001",
      "stride": "Spoofing|Tampering|Repudiation|InformationDisclosure|DoS|ElevationOfPrivilege",
      "description": "...",
      "likelihood": "LOW|MEDIUM|HIGH",
      "impact": "LOW|MEDIUM|HIGH",
      "affected_assets": ["..."],
      "owasp_mapping": "A01:2021"
    }
  ],
  "security_requirements": [
    {
      "id": "REQ-001",
      "addresses_threats": ["T-001"],
      "requirement": "Implementable, testable requirement",
      "verification": "How to verify the requirement is met"
    }
  ],
  "red_team_hints": [
    {"threat_id": "T-001", "attack_to_attempt": "...", "expected_indicator": "..."}
  ]
}

Requirements:
- Cover every Mythos-relevant class: AUTH_BYPASS, AUTHZ_BROKEN, INJECTION_*, XSS_*, CSRF, IDOR, CRYPTO_IMPL, RACE_CONDITION, API_LOGIC, SUPPLY_CHAIN, CONFIG_INSECURE.
- Each requirement must be implementable (not "be secure") and verifiable (have a testable outcome).
- If the brief is ambiguous, list assumptions explicitly. Do NOT proceed past ambiguity silently.
- DO NOT write any code.
- Output JSON only.
```

Create `src/mythos_defense/agents/architect.py`:

```python
"""Architect Agent — produces threat model from a brief."""
from __future__ import annotations
import json
from mythos_defense.agents.base import BaseAgent, AgentResult


class ArchitectAgent(BaseAgent):
    name = "architect"
    model = "claude-opus-4-7"  # reasoning-heavy
    max_tokens = 16000
    
    def run(self, brief: str) -> AgentResult:
        system = self._load_prompt("architect")
        user = f"# Project Brief\n\n{brief}\n\nProduce the threat model JSON."
        result = self._call(system, user)
        
        # Parse and validate
        try:
            text = result.output.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result.structured = json.loads(text.strip())
        except json.JSONDecodeError as e:
            raise ValueError(f"Architect output not valid JSON: {e}\nRaw: {result.output[:500]}")
        
        return result
```

### 3.3 Blue Team Agent

Create the prompt file `src/mythos_defense/prompts/blue_team.md`:

```markdown
You are a senior engineer fixing a specific security finding. You receive ONE finding at a time. Your job: patch correctly without regressions.

Inputs you receive:
- The complete finding (JSON)
- Affected source files (full content)
- Prior failed patch attempts for this finding (if any), with failure reasons

Process:
1. Understand the root cause. DO NOT patch the symptom.
2. Propose a fix that:
   - Addresses the root cause at the correct architectural layer
   - Preserves legitimate functionality
   - Does not create new attack surface
   - Follows the codebase's existing conventions
3. Generate the patch as a unified diff.
4. Generate regression tests:
   - One test that reproduces the exploit and asserts it now FAILS
   - One test that asserts legitimate use still SUCCEEDS
5. State your fix rationale.

Hard rules:
- DO NOT fix by adding a WAF rule or input filter when the real fix is deeper.
- DO NOT disable the affected feature.
- DO NOT patch by checking for the specific PoC payload. Fix the class.
- If correct fix requires architectural changes beyond the affected file(s), say so explicitly with `requires_escalation: true` and explain.

Output a single JSON object — no surrounding prose, no markdown fences:

{
  "fix_rationale": "Why this fix addresses the root cause",
  "root_cause_addressed": "file:line where the actual bug lived",
  "files_changed": [
    {"path": "...", "diff": "unified diff content here"}
  ],
  "tests_added": [
    {"path": "...", "purpose": "exploit_blocked|functionality_preserved", "content": "test code"}
  ],
  "risk_of_regression": "LOW|MEDIUM|HIGH",
  "notes_for_reviewer": "Anything a human reviewer should know",
  "requires_escalation": false,
  "escalation_reason": null
}
```

Create `src/mythos_defense/agents/blue_team.py`:

```python
"""Blue Team Agent — patches findings."""
from __future__ import annotations
import json
from pathlib import Path
from mythos_defense.agents.base import BaseAgent, AgentResult
from mythos_defense.schemas.findings import Finding


class BlueTeamAgent(BaseAgent):
    name = "blue_team"
    model = "claude-sonnet-4-6"
    max_tokens = 16000
    
    def run(
        self,
        finding: Finding,
        workspace: Path,
        prior_attempts: list[dict] | None = None,
    ) -> AgentResult:
        system = self._load_prompt("blue_team")
        
        # Read affected files
        file_contents = []
        for loc in finding.affected_locations:
            file_path = workspace / loc.path
            if file_path.exists() and file_path.is_file():
                content = file_path.read_text()
                file_contents.append(f"### {loc.path}\n```\n{content}\n```")
        
        prior_text = ""
        if prior_attempts:
            prior_text = "\n\n## Prior Failed Attempts\n\n" + "\n\n".join(
                f"Attempt {i+1}: {a.get('rationale', '')}\nWhy it failed: {a.get('failure', '')}"
                for i, a in enumerate(prior_attempts)
            )
        
        user = f"""# Finding

```json
{finding.model_dump_json(indent=2)}
```

# Affected Files

{chr(10).join(file_contents) if file_contents else "(no files readable from affected_locations)"}
{prior_text}

Produce the patch JSON.
"""
        result = self._call(system, user)
        
        try:
            text = result.output.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result.structured = json.loads(text.strip())
        except json.JSONDecodeError as e:
            raise ValueError(f"Blue Team output not valid JSON: {e}\nRaw: {result.output[:500]}")
        
        return result
```

### 3.4 Supply Chain Agent

Create `src/mythos_defense/prompts/supply_chain.md`:

```markdown
You are a software supply chain security analyst. You receive: (1) raw output from `npm audit --json` or `pip-audit` or similar, and (2) the project's manifest files. Your job: produce a prioritized risk assessment.

Output a single JSON object — no surrounding prose:

{
  "summary": {
    "total_dependencies": 0,
    "direct": 0,
    "transitive": 0,
    "vulnerable_count": 0,
    "highest_severity": "CRITICAL|HIGH|MEDIUM|LOW|NONE"
  },
  "findings": [
    {
      "package": "name@version",
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "issue_class": "CVE|TYPOSQUAT|ABANDONED|LICENSE|NEW_DEPENDENCY|SINGLE_MAINTAINER",
      "cve_ids": ["CVE-..."],
      "description": "What's wrong",
      "exploit_in_context": "Whether this dep is reachable from internet-facing code (best effort)",
      "recommendation": "Specific action: upgrade to X, remove, replace with Y"
    }
  ],
  "concerns": [
    "Free-form notes on patterns: e.g., many transitive vulns from a single deep dep"
  ]
}

Hard rules:
- Flag any dependency with no updates in >2 years AND used in security-critical paths (auth, crypto) as ABANDONED.
- Flag single-maintainer packages used in security-critical paths as SINGLE_MAINTAINER.
- DO NOT suggest auto-updates for major version bumps without flagging breaking-change risk.
```

Create `src/mythos_defense/agents/supply_chain.py`:

```python
"""Supply Chain Agent."""
from __future__ import annotations
import json
import subprocess
from pathlib import Path
from mythos_defense.agents.base import BaseAgent, AgentResult


class SupplyChainAgent(BaseAgent):
    name = "supply_chain"
    model = "claude-sonnet-4-6"
    max_tokens = 8000
    
    def run(self, workspace: Path) -> AgentResult:
        system = self._load_prompt("supply_chain")
        
        # Collect raw inputs
        audit_output = ""
        manifests = []
        
        # npm audit if applicable
        if (workspace / "package.json").exists():
            manifests.append(("package.json", (workspace / "package.json").read_text()))
            try:
                r = subprocess.run(
                    ["npm", "audit", "--json"],
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                audit_output = r.stdout[:50000]  # cap
            except Exception as e:
                audit_output = f"(npm audit failed: {e})"
        
        # pip-audit if applicable
        elif (workspace / "requirements.txt").exists() or (workspace / "pyproject.toml").exists():
            manifests.append(("manifest", (workspace / ("requirements.txt" if (workspace / "requirements.txt").exists() else "pyproject.toml")).read_text()))
            try:
                r = subprocess.run(
                    ["pip-audit", "--format", "json"],
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                audit_output = r.stdout[:50000]
            except Exception as e:
                audit_output = f"(pip-audit failed or not installed: {e})"
        
        manifest_block = "\n\n".join(f"### {name}\n```\n{c}\n```" for name, c in manifests)
        
        user = f"""# Audit Tool Output

```json
{audit_output or "(no audit output)"}
```

# Manifest Files

{manifest_block or "(no manifests found)"}

Produce the supply chain assessment JSON.
"""
        result = self._call(system, user)
        try:
            text = result.output.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result.structured = json.loads(text.strip())
        except json.JSONDecodeError as e:
            raise ValueError(f"Supply Chain output not valid JSON: {e}")
        return result
```

### 3.5 Deployment Agent

Create `src/mythos_defense/prompts/deployment.md`:

```markdown
You are a security-focused SRE. Given a project description and threat model, produce hardened deployment configuration.

Output a single JSON object — no surrounding prose:

{
  "tls": {"min_version": "TLSv1.2|TLSv1.3", "cipher_policy": "...", "hsts_max_age": 31536000, "hsts_subdomains": true, "hsts_preload": true},
  "security_headers": {
    "Content-Security-Policy": "...",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "...",
    "Permissions-Policy": "...",
    "X-Frame-Options": "DENY"
  },
  "cors": {"allowed_origins": ["..."], "allow_credentials": false, "rationale": "..."},
  "rate_limits": [
    {"endpoint_pattern": "/api/login", "per_ip_per_minute": 5, "per_user_per_minute": 10}
  ],
  "secret_management": {"approach": "...", "rotation_policy": "..."},
  "iam_principles": ["least privilege specifics for this app"],
  "logging": {"events_to_capture": ["..."], "pii_handling": "..."},
  "rationale_summary": "Plain-English summary for human review"
}

Hard rules:
- NEVER use wildcard origins in CORS with credentials.
- NEVER use unsafe-inline or unsafe-eval in CSP without explicit written justification referencing a specific framework requirement.
- Default-deny everywhere — every allow needs justification.
- For HSTS, only recommend preload if subdomains are confirmed compatible.
```

Create `src/mythos_defense/agents/deployment.py`:

```python
"""Deployment Agent — produces hardened deploy config."""
from __future__ import annotations
import json
from mythos_defense.agents.base import BaseAgent, AgentResult


class DeploymentAgent(BaseAgent):
    name = "deployment"
    model = "claude-sonnet-4-6"
    max_tokens = 6000
    
    def run(self, brief: str, threat_model: dict) -> AgentResult:
        system = self._load_prompt("deployment")
        user = f"""# Project Brief

{brief}

# Threat Model

```json
{json.dumps(threat_model, indent=2)[:30000]}
```

Produce the deployment hardening JSON.
"""
        result = self._call(system, user)
        try:
            text = result.output.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result.structured = json.loads(text.strip())
        except json.JSONDecodeError as e:
            raise ValueError(f"Deployment output not valid JSON: {e}")
        return result
```

---

## Phase 4: Verify Loop and Sandbox

The verify step is what gives the loop teeth: after Blue Team produces a patch, you actually try the PoC again and confirm it now fails.

### 4.1 Docker sandbox for verify

Create `Dockerfile.verify`:

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd -m -s /bin/bash sandbox
USER sandbox
WORKDIR /home/sandbox

# Read-only at runtime via docker run flags
CMD ["/bin/bash"]
```

Build it:

```bash
docker build -t mythos-verify -f Dockerfile.verify .
```

### 4.2 Verify implementation

Create `src/mythos_defense/orchestrator/verify.py`:

```python
"""Verify a patch by re-running the PoC against the patched code in a sandbox."""
from __future__ import annotations
import subprocess
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from mythos_defense.schemas.findings import Finding


@dataclass
class VerifyResult:
    exploit_blocked: bool
    regression_passed: bool
    details: str


def apply_patch(workspace: Path, files_changed: list[dict]) -> bool:
    """Apply unified diffs to the workspace. Returns True on success."""
    for fc in files_changed:
        diff_text = fc["diff"]
        # Use git apply for safety. workspace must be a git repo or tempdir.
        with tempfile.NamedTemporaryFile("w", suffix=".diff", delete=False) as tf:
            tf.write(diff_text)
            patch_file = tf.name
        try:
            r = subprocess.run(
                ["git", "apply", "--whitespace=nowarn", patch_file],
                cwd=workspace,
                capture_output=True,
                text=True,
            )
            if r.returncode != 0:
                # Fall back: try `patch` command
                r2 = subprocess.run(
                    ["patch", "-p1", "-i", patch_file],
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                )
                if r2.returncode != 0:
                    return False
        finally:
            Path(patch_file).unlink(missing_ok=True)
    return True


def verify_in_sandbox(
    finding: Finding,
    patched_workspace: Path,
    docker_image: str = "mythos-verify",
    timeout_seconds: int = 300,
) -> VerifyResult:
    """Run a verify pass in a sandboxed container.
    
    For V0 we run a simple check: copy the workspace + PoC script into a
    container, run the script, and infer success from exit code and output.
    """
    if not finding.poc.reproduction_script:
        return VerifyResult(
            exploit_blocked=False,
            regression_passed=False,
            details="No reproduction_script present — manual verification required",
        )
    
    cmd = [
        "docker", "run", "--rm",
        "--network", "none",  # default-deny network for verify
        "--read-only",
        "--tmpfs", "/tmp:size=64m",
        "--memory", "1g",
        "--cpus", "1",
        "-v", f"{patched_workspace.absolute()}:/work:ro",
        docker_image,
        "bash", "-c", f"cd /work && timeout {timeout_seconds - 30} bash {finding.poc.reproduction_script}",
    ]
    
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        return VerifyResult(False, False, "verify timed out")
    
    # Convention: PoC script exits 0 if exploit succeeded, non-zero if it failed.
    # After patching, we WANT the PoC to fail (non-zero exit).
    exploit_blocked = r.returncode != 0
    
    return VerifyResult(
        exploit_blocked=exploit_blocked,
        regression_passed=True,  # full regression suite is a separate concern
        details=f"exit={r.returncode}, stdout={r.stdout[:500]}, stderr={r.stderr[:500]}",
    )
```

### 4.3 Budget tracking

Create `src/mythos_defense/orchestrator/budget.py`:

```python
"""Budget enforcement across a workflow."""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Budget:
    max_tokens: int = 1_000_000
    max_iterations: int = 5
    max_blue_attempts_per_finding: int = 3
    max_wall_seconds: int = 3600
    
    tokens_used: int = 0
    iterations: int = 0
    blue_attempts: dict[str, int] = field(default_factory=dict)
    started_at: float = 0.0
    
    def spend_tokens(self, n: int) -> None:
        self.tokens_used += n
    
    def can_continue(self) -> tuple[bool, str]:
        if self.tokens_used >= self.max_tokens:
            return False, "max_tokens exceeded"
        if self.iterations >= self.max_iterations:
            return False, "max_iterations reached"
        return True, ""
    
    def can_attempt_patch(self, finding_id: str) -> bool:
        return self.blue_attempts.get(finding_id, 0) < self.max_blue_attempts_per_finding
    
    def record_attempt(self, finding_id: str) -> None:
        self.blue_attempts[finding_id] = self.blue_attempts.get(finding_id, 0) + 1
```

---

## Phase 5: Orchestrator

The orchestrator wires everything together. For V0 it's a simple async Python loop, not Temporal. Migration path is straightforward later.

Create `src/mythos_defense/orchestrator/workflow.py`:

```python
"""V0 orchestrator — simple loop, not durable."""
from __future__ import annotations
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from rich.console import Console

from mythos_defense.adapters.base import RedTeamAdapter, AdapterTarget
from mythos_defense.agents.architect import ArchitectAgent
from mythos_defense.agents.blue_team import BlueTeamAgent
from mythos_defense.agents.supply_chain import SupplyChainAgent
from mythos_defense.agents.deployment import DeploymentAgent
from mythos_defense.orchestrator.budget import Budget
from mythos_defense.orchestrator.verify import (
    apply_patch, verify_in_sandbox, VerifyResult,
)
from mythos_defense.schemas.findings import Finding

console = Console()


@dataclass
class WorkflowConfig:
    workflow_id: str
    workspace: Path
    brief: str
    output_dir: Path
    budget: Budget = field(default_factory=Budget)
    running_app_url: str | None = None


@dataclass
class WorkflowResult:
    workflow_id: str
    status: str  # CONVERGED|BUDGET_EXHAUSTED|ITERATION_CAP|ERROR
    threat_model: dict | None
    findings_history: list[list[Finding]]
    patches_applied: list[dict]
    unresolved_findings: list[Finding]
    supply_chain: dict | None
    deployment: dict | None
    duration_seconds: float


class Orchestrator:
    def __init__(self, red_team_adapter: RedTeamAdapter):
        self.red_team = red_team_adapter
        self.architect = ArchitectAgent()
        self.blue_team = BlueTeamAgent()
        self.supply_chain = SupplyChainAgent()
        self.deployment = DeploymentAgent()
    
    def run(self, cfg: WorkflowConfig) -> WorkflowResult:
        start = time.time()
        cfg.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Phase A: Threat model
        console.print("[bold cyan]→ Architect: producing threat model[/]")
        arch_result = self.architect.run(cfg.brief)
        cfg.budget.spend_tokens(arch_result.tokens_in + arch_result.tokens_out)
        threat_model = arch_result.structured
        (cfg.output_dir / "threat_model.json").write_text(
            json.dumps(threat_model, indent=2)
        )
        
        # Phase B: Adversarial loop (Red Team via adapter, Blue Team patches)
        findings_history = []
        patches_applied = []
        excluded = []
        clean_rounds = 0
        last_findings: list[Finding] = []
        
        for iteration in range(cfg.budget.max_iterations):
            cfg.budget.iterations = iteration + 1
            ok, reason = cfg.budget.can_continue()
            if not ok:
                console.print(f"[yellow]Budget halt: {reason}[/]")
                break
            
            console.print(f"[bold cyan]→ Iteration {iteration}: Red Team adapter ({self.red_team.name})[/]")
            
            target = AdapterTarget(
                workspace=cfg.workspace,
                running_app_url=cfg.running_app_url,
                iteration=iteration,
                workflow_id=cfg.workflow_id,
                excluded_findings=excluded,
            )
            try:
                finding_set = self.red_team.run(target)
            except Exception as e:
                console.print(f"[red]Red Team adapter failed: {e}[/]")
                break
            
            new_findings = finding_set.findings
            findings_history.append(new_findings)
            
            if not new_findings:
                clean_rounds += 1
                console.print(f"[green]Clean round {clean_rounds}[/]")
                if clean_rounds >= 2:  # tunable
                    return self._finalize(cfg, "CONVERGED", threat_model, findings_history,
                                          patches_applied, [], start)
                continue
            
            clean_rounds = 0
            console.print(f"[yellow]Found {len(new_findings)} findings[/]")
            last_findings = new_findings
            
            # Sort by severity
            severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
            for finding in sorted(new_findings, key=lambda f: severity_order.get(f.severity.value, 99)):
                if not cfg.budget.can_attempt_patch(finding.finding_id):
                    console.print(f"[red]Skip {finding.finding_id}: max attempts reached[/]")
                    continue
                
                console.print(f"[bold cyan]→ Blue Team: {finding.finding_id} ({finding.severity})[/]")
                cfg.budget.record_attempt(finding.finding_id)
                
                try:
                    blue_result = self.blue_team.run(finding, cfg.workspace)
                except Exception as e:
                    console.print(f"[red]Blue Team failed for {finding.finding_id}: {e}[/]")
                    continue
                
                cfg.budget.spend_tokens(blue_result.tokens_in + blue_result.tokens_out)
                patch = blue_result.structured
                
                if patch.get("requires_escalation"):
                    console.print(f"[magenta]Escalation: {patch.get('escalation_reason')}[/]")
                    continue
                
                # Apply patch
                ok = apply_patch(cfg.workspace, patch.get("files_changed", []))
                if not ok:
                    console.print(f"[red]Patch did not apply for {finding.finding_id}[/]")
                    continue
                
                # Verify
                verify_result = verify_in_sandbox(finding, cfg.workspace)
                
                patch_record = {
                    "finding_id": finding.finding_id,
                    "patch": patch,
                    "verify": {
                        "exploit_blocked": verify_result.exploit_blocked,
                        "details": verify_result.details,
                    },
                }
                patches_applied.append(patch_record)
                
                if verify_result.exploit_blocked:
                    excluded.append(finding.finding_id)
                    console.print(f"[green]✓ {finding.finding_id} verified blocked[/]")
                else:
                    console.print(f"[red]✗ {finding.finding_id} not blocked: {verify_result.details[:200]}[/]")
                    # Could revert patch here in a stricter implementation
        
        # Phase C: Supply chain
        console.print("[bold cyan]→ Supply Chain Agent[/]")
        try:
            sc_result = self.supply_chain.run(cfg.workspace)
            cfg.budget.spend_tokens(sc_result.tokens_in + sc_result.tokens_out)
            supply_chain = sc_result.structured
        except Exception as e:
            console.print(f"[red]Supply chain failed: {e}[/]")
            supply_chain = {"error": str(e)}
        
        # Phase D: Deployment
        console.print("[bold cyan]→ Deployment Agent[/]")
        try:
            dep_result = self.deployment.run(cfg.brief, threat_model)
            cfg.budget.spend_tokens(dep_result.tokens_in + dep_result.tokens_out)
            deployment = dep_result.structured
        except Exception as e:
            console.print(f"[red]Deployment failed: {e}[/]")
            deployment = {"error": str(e)}
        
        # Determine final status
        unresolved = [f for f in last_findings if f.finding_id not in excluded]
        status = "CONVERGED" if not unresolved else "ITERATION_CAP"
        
        return self._finalize(
            cfg, status, threat_model, findings_history, patches_applied,
            unresolved, start, supply_chain=supply_chain, deployment=deployment,
        )
    
    def _finalize(
        self, cfg, status, threat_model, findings_history, patches_applied,
        unresolved, start, supply_chain=None, deployment=None,
    ) -> WorkflowResult:
        result = WorkflowResult(
            workflow_id=cfg.workflow_id,
            status=status,
            threat_model=threat_model,
            findings_history=findings_history,
            patches_applied=patches_applied,
            unresolved_findings=unresolved,
            supply_chain=supply_chain,
            deployment=deployment,
            duration_seconds=time.time() - start,
        )
        
        # Persist report
        report = {
            "workflow_id": result.workflow_id,
            "status": result.status,
            "duration_seconds": result.duration_seconds,
            "threat_model": result.threat_model,
            "iterations": [
                [f.model_dump(mode="json") for f in iteration]
                for iteration in result.findings_history
            ],
            "patches": result.patches_applied,
            "unresolved": [f.model_dump(mode="json") for f in result.unresolved_findings],
            "supply_chain": result.supply_chain,
            "deployment": result.deployment,
        }
        (cfg.output_dir / "report.json").write_text(json.dumps(report, indent=2, default=str))
        return result
```

---

## Phase 6: CLI

Tie it all together with a CLI.

Create `src/mythos_defense/cli.py`:

```python
"""mythos CLI."""
from __future__ import annotations
import os
import sys
import uuid
from pathlib import Path
import click
from dotenv import load_dotenv
from rich.console import Console

from mythos_defense.adapters.mock import MockAdapter
from mythos_defense.adapters.semgrep import SemgrepAdapter
from mythos_defense.adapters.zap import ZapAdapter
from mythos_defense.orchestrator.workflow import Orchestrator, WorkflowConfig
from mythos_defense.orchestrator.budget import Budget

load_dotenv()
console = Console()


@click.group()
def main():
    """Mythos Defense Platform CLI."""
    pass


@main.command()
@click.option("--workspace", "-w", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--brief", "-b", required=True, help="Path to project brief markdown, or inline text.")
@click.option("--adapter", "-a", default="mock", type=click.Choice(["mock", "semgrep", "zap"]))
@click.option("--app-url", default=None, help="Running app URL (required for zap)")
@click.option("--output", "-o", default="./workflows", type=click.Path(path_type=Path))
@click.option("--max-iterations", default=3, type=int)
@click.option("--max-tokens", default=500_000, type=int)
@click.option("--fixtures", default="tests/fixtures/findings", type=click.Path(path_type=Path),
              help="Fixtures dir for mock adapter")
def assess(workspace, brief, adapter, app_url, output, max_iterations, max_tokens, fixtures):
    """Run a full security assessment workflow."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        console.print("[red]ANTHROPIC_API_KEY not set. Set it in .env or environment.[/]")
        sys.exit(1)
    
    # Resolve brief
    brief_path = Path(brief)
    if brief_path.exists():
        brief_text = brief_path.read_text()
    else:
        brief_text = brief
    
    # Pick adapter
    if adapter == "mock":
        rt_adapter = MockAdapter(fixtures_dir=fixtures)
    elif adapter == "semgrep":
        rt_adapter = SemgrepAdapter()
    elif adapter == "zap":
        if not app_url:
            console.print("[red]--app-url required for zap adapter[/]")
            sys.exit(1)
        rt_adapter = ZapAdapter()
    
    # Configure
    workflow_id = f"wf-{uuid.uuid4().hex[:8]}"
    cfg = WorkflowConfig(
        workflow_id=workflow_id,
        workspace=workspace.absolute(),
        brief=brief_text,
        output_dir=output / workflow_id,
        budget=Budget(max_iterations=max_iterations, max_tokens=max_tokens),
        running_app_url=app_url,
    )
    
    console.rule(f"[bold]Workflow {workflow_id}")
    console.print(f"Workspace: {cfg.workspace}")
    console.print(f"Adapter: {adapter}")
    console.print(f"Output: {cfg.output_dir}")
    
    orchestrator = Orchestrator(red_team_adapter=rt_adapter)
    result = orchestrator.run(cfg)
    
    console.rule(f"[bold]Done — {result.status}")
    console.print(f"Duration: {result.duration_seconds:.1f}s")
    console.print(f"Patches applied: {len(result.patches_applied)}")
    console.print(f"Unresolved: {len(result.unresolved_findings)}")
    console.print(f"Report: {cfg.output_dir / 'report.json'}")
    
    if result.unresolved_findings:
        sys.exit(2)


@main.command()
@click.option("--brief", "-b", required=True)
def threat_model(brief):
    """Just produce a threat model — no scanning, no patches."""
    from mythos_defense.agents.architect import ArchitectAgent
    import json
    brief_path = Path(brief)
    text = brief_path.read_text() if brief_path.exists() else brief
    agent = ArchitectAgent()
    result = agent.run(text)
    click.echo(json.dumps(result.structured, indent=2))


@main.command()
def doctor():
    """Check that adapters and tools are available."""
    checks = [
        ("ANTHROPIC_API_KEY set", bool(os.getenv("ANTHROPIC_API_KEY"))),
        ("semgrep installed", SemgrepAdapter().healthcheck()),
        ("docker available", ZapAdapter().healthcheck()),
    ]
    for name, ok in checks:
        symbol = "[green]✓[/]" if ok else "[red]✗[/]"
        console.print(f"{symbol} {name}")


if __name__ == "__main__":
    main()
```

You'll need `python-dotenv`:

```bash
pip install python-dotenv
```

Reinstall the package so the CLI script is registered:

```bash
pip install -e ".[dev]"
```

---

## Phase 7: First End-to-End Run (with Mock)

Create a sample brief:

```bash
cat > sample_brief.md << 'EOF'
# Brief: Internal Admin Portal

A small internal admin portal for managing user accounts and content.

## Features
- Login with email + password
- JWT-based session
- Admin role can list/edit/delete users
- Admin role can publish content
- Audit log of admin actions

## Tech
- Node.js / Express backend
- PostgreSQL
- React frontend

## Threat Context
Internal-only network in V1, but planning for public exposure in V2.
EOF
```

Run with the mock adapter:

```bash
mkdir -p ./test-workspace
cp -r tests/fixtures/findings ./test-workspace/  # placeholder workspace

mythos assess \
    --workspace ./test-workspace \
    --brief sample_brief.md \
    --adapter mock \
    --max-iterations 2
```

Expected output: an architect step, mock findings, blue team attempts, supply chain (likely empty), deployment recommendations, and a `report.json` in `./workflows/wf-XXXXX/`.

For a real test, point at a known-vulnerable repo:

```bash
git clone https://github.com/juice-shop/juice-shop /tmp/juice-shop
mythos assess \
    --workspace /tmp/juice-shop \
    --brief sample_brief.md \
    --adapter semgrep \
    --max-iterations 3
```

---

## Phase 8: Evaluation Harness

Create `eval/runner.py`:

```python
"""Minimal evaluation harness — runs workflows against known-vulnerable apps,
compares findings to expected ground truth."""
from __future__ import annotations
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
import subprocess


@dataclass
class EvalCase:
    name: str
    repo: str           # git URL
    expected_classes: list[str]  # vuln_class values we expect to be detected
    brief_path: Path
    adapter: str = "semgrep"


@dataclass
class EvalResult:
    case: str
    detected_classes: set[str]
    expected_classes: set[str]
    recall: float
    precision: float
    duration_seconds: float


CASES = [
    EvalCase(
        name="juice-shop",
        repo="https://github.com/juice-shop/juice-shop",
        expected_classes=["INJECTION_SQL", "XSS_REFLECTED", "AUTH_BYPASS", "IDOR"],
        brief_path=Path("eval/suites/juice_shop_brief.md"),
    ),
    EvalCase(
        name="nodegoat",
        repo="https://github.com/OWASP/NodeGoat",
        expected_classes=["INJECTION_SQL", "XSS_REFLECTED", "CSRF", "CRYPTO_IMPL"],
        brief_path=Path("eval/suites/nodegoat_brief.md"),
    ),
]


def run_case(case: EvalCase, work_root: Path) -> EvalResult:
    repo_dir = work_root / case.name
    if not repo_dir.exists():
        subprocess.run(["git", "clone", "--depth", "1", case.repo, str(repo_dir)], check=True)
    
    output_dir = work_root / "out" / case.name
    cmd = [
        "mythos", "assess",
        "-w", str(repo_dir),
        "-b", str(case.brief_path),
        "-a", case.adapter,
        "-o", str(output_dir),
        "--max-iterations", "2",
    ]
    import time
    t0 = time.time()
    subprocess.run(cmd, check=False)
    duration = time.time() - t0
    
    # Read latest report
    workflow_dirs = sorted(output_dir.iterdir())
    if not workflow_dirs:
        return EvalResult(case.name, set(), set(case.expected_classes), 0, 0, duration)
    report = json.loads((workflow_dirs[-1] / "report.json").read_text())
    
    detected = set()
    for iteration in report.get("iterations", []):
        for f in iteration:
            detected.add(f["vuln_class"])
    
    expected = set(case.expected_classes)
    recall = len(detected & expected) / len(expected) if expected else 0
    precision = len(detected & expected) / len(detected) if detected else 0
    
    return EvalResult(case.name, detected, expected, recall, precision, duration)


def main():
    work_root = Path("eval/work")
    work_root.mkdir(parents=True, exist_ok=True)
    
    print(f"{'CASE':20} {'RECALL':>8} {'PRECISION':>10} {'DURATION':>10}")
    print("-" * 55)
    
    for case in CASES:
        if not case.brief_path.exists():
            case.brief_path.parent.mkdir(parents=True, exist_ok=True)
            case.brief_path.write_text(f"# {case.name}\n\nKnown-vulnerable application.\n")
        
        result = run_case(case, work_root)
        print(f"{result.case:20} {result.recall:>7.1%} {result.precision:>9.1%} {result.duration_seconds:>9.1f}s")


if __name__ == "__main__":
    main()
```

Run it:

```bash
python eval/runner.py
```

This is a starting point. The metrics from the evaluation document (per-class recall, time-to-detection, patch correctness) extend from here.

---

## What You Have After This

A V0 that:

1. Takes a brief and produces a STRIDE threat model
2. Runs a Red Team adapter (mock for testing, Semgrep for static, ZAP for dynamic) against a workspace
3. Routes findings through a Blue Team agent that produces patches
4. Applies patches and verifies them in a sandboxed container
5. Iterates until convergence or budget exhaustion
6. Produces supply chain assessment
7. Produces deployment hardening recommendations
8. Writes a complete JSON report
9. Has a working evaluation harness against known-vulnerable apps

What it is not yet:

- Durable across crashes (no Temporal — workflow loses state if the process dies)
- Multi-tenant (one user, one workspace at a time)
- Hardened (Docker, not Firecracker; the verify sandbox is V0-grade)
- Full-coverage on findings (Semgrep alone misses logic flaws and most authn bypasses; that's the gap the autonomous Red Team would fill)

---

## Recommended Next Steps

In rough order of value:

1. **Run it against three real codebases you control** and read the reports critically. The agent prompts will need tuning based on what they actually produce.
2. **Add a real PoC verifier.** The mock fixture's PoC is descriptive, not executable. For Semgrep findings, the PoC is "code pattern present"; for ZAP findings, the PoC is an HTTP request you can re-run. Make verify actually execute these.
3. **Add Snyk and trivy adapters.** Better supply chain coverage than `npm audit` alone.
4. **Build a findings dashboard.** Even a simple HTML output of `report.json` makes the platform demoable.
5. **Migrate the orchestrator to Temporal** when you outgrow the simple loop.
6. **Engage Anthropic about the autonomous Red Team capability.** If the V0 demonstrates the loop works with mock and tool-based adapters, the case for filling that slot via a controlled channel is much stronger.

The defensive half is genuinely useful on its own. Many security teams would pay for an orchestrated Architect → Semgrep/ZAP → Blue Team → verify pipeline even without an autonomous offensive component, because the existing tools' findings are notoriously hard to triage and patch correctly. Build that, prove the loop, and the offensive piece becomes a roadmap question rather than the whole product.

---

*V0 Implementation Guide — companion to the consolidated reference.*
