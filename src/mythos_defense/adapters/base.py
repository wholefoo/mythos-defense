"""Red Team adapter contract."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from mythos_defense.schemas.findings import FindingSet


@dataclass
class AdapterTarget:
    """What the adapter is asked to test."""
    workspace: Path
    iteration: int = 0
    workflow_id: str = ""
    excluded_findings: list[str] = field(default_factory=list)
    config: dict = field(default_factory=dict)


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
