"""Semgrep adapter — runs semgrep, maps results to Finding schema."""
from __future__ import annotations
import json
import subprocess
import uuid
from mythos_defense.adapters.base import RedTeamAdapter, AdapterTarget, AdapterError
from mythos_defense.schemas.findings import (
    Finding, FindingSet, Severity, VulnClass, CodeLocation, ProofOfConcept,
)

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
        self.config = config

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
        if result.returncode not in (0, 1):
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
