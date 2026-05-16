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
