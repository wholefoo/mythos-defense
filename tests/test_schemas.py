"""Tests for Pydantic schemas."""
import pytest
from mythos_defense.schemas.findings import (
    Finding, FindingSet, CodeLocation, ProofOfConcept,
    Severity, VulnClass,
)


def _make_finding(**overrides) -> dict:
    """Build a valid finding dict for testing."""
    base = {
        "finding_id": "TEST-001",
        "source": "test",
        "severity": "HIGH",
        "vuln_class": "INJECTION_SQL",
        "title": "SQL Injection in login endpoint",
        "description": "User input is concatenated directly into SQL query without parameterization.",
        "affected_locations": [{"path": "src/auth.py", "line_start": 42}],
        "root_cause": "String concatenation used instead of parameterized queries in database layer.",
        "poc": {
            "poc_type": "http_request",
            "steps": ["Send POST to /login with payload: ' OR 1=1 --"],
            "expected_evidence": "HTTP 200 with admin session token",
        },
    }
    base.update(overrides)
    return base


def test_finding_valid():
    f = Finding(**_make_finding())
    assert f.finding_id == "TEST-001"
    assert f.severity == Severity.HIGH


def test_finding_invalid_severity():
    with pytest.raises(Exception):
        Finding(**_make_finding(severity="EXTREME"))


def test_finding_title_too_short():
    with pytest.raises(Exception):
        Finding(**_make_finding(title="Short"))


def test_code_location_line_end_before_start():
    with pytest.raises(Exception):
        CodeLocation(path="foo.py", line_start=10, line_end=5)


def test_code_location_valid():
    loc = CodeLocation(path="src/app.py", line_start=1, line_end=10)
    assert loc.line_end == 10


def test_finding_set():
    fs = FindingSet(
        workflow_id="wf-test",
        iteration=0,
        source="mock",
        findings=[Finding(**_make_finding())],
    )
    assert len(fs.findings) == 1
    assert fs.budget_consumed == {}


def test_finding_discovered_at_has_timezone():
    f = Finding(**_make_finding())
    assert f.discovered_at.tzinfo is not None
