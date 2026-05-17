"""Tests for budget enforcement."""
import time
from mythos_defense.orchestrator.budget import Budget


def test_budget_token_limit():
    b = Budget(max_tokens=100)
    b.spend_tokens(50)
    ok, _ = b.can_continue()
    assert ok is True

    b.spend_tokens(60)
    ok, reason = b.can_continue()
    assert ok is False
    assert reason == "max_tokens exceeded"


def test_budget_iteration_limit():
    b = Budget(max_iterations=3)
    b.iterations = 2
    ok, _ = b.can_continue()
    assert ok is True

    b.iterations = 3
    ok, reason = b.can_continue()
    assert ok is False
    assert reason == "max_iterations reached"


def test_budget_wall_time():
    b = Budget(max_wall_seconds=1)
    b.started_at = time.time() - 2  # Already 2s past
    ok, reason = b.can_continue()
    assert ok is False
    assert reason == "wall_time_exceeded"


def test_budget_patch_attempts():
    b = Budget(max_blue_attempts_per_finding=2)
    assert b.can_attempt_patch("f-1") is True
    b.record_attempt("f-1")
    assert b.can_attempt_patch("f-1") is True
    b.record_attempt("f-1")
    assert b.can_attempt_patch("f-1") is False
    # Different finding is unaffected
    assert b.can_attempt_patch("f-2") is True
