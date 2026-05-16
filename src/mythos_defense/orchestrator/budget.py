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
