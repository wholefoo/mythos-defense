"""Finding schema — the contract between Red Team sources and defensive agents."""
from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
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
        description="Path to a script (relative to artifacts dir) that reproduces the issue",
    )
    expected_evidence: str = Field(description="What you'll see when the exploit succeeds")
    artifacts: list[str] = Field(
        default_factory=list,
        description="Paths to evidence artifacts (response.json, screenshot, log)",
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
        description="Why this is broken at the architectural/code level",
    )

    poc: ProofOfConcept

    impact_confidentiality: Severity = Severity.LOW
    impact_integrity: Severity = Severity.LOW
    impact_availability: Severity = Severity.LOW

    cwe_ids: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)

    discovered_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))

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
    budget_consumed: dict[str, Any] = Field(default_factory=dict)
