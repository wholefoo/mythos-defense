from pathlib import Path
from mythos_defense.adapters.mock import MockAdapter
from mythos_defense.adapters.base import AdapterTarget

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "findings"


def test_mock_adapter_loads_fixtures():
    adapter = MockAdapter(fixtures_dir=FIXTURES_DIR)
    target = AdapterTarget(
        workspace=Path("."),
        workflow_id="test-001",
        iteration=0,
    )
    result = adapter.run(target)
    assert len(result.findings) >= 1
    assert result.findings[0].finding_id == "MOCK-2026-0001"


def test_mock_adapter_honors_exclusions():
    adapter = MockAdapter(fixtures_dir=FIXTURES_DIR)
    target = AdapterTarget(
        workspace=Path("."),
        workflow_id="test-001",
        iteration=1,
        excluded_findings=["MOCK-2026-0001"],
    )
    result = adapter.run(target)
    assert all(f.finding_id != "MOCK-2026-0001" for f in result.findings)
