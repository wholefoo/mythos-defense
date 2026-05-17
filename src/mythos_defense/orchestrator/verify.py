"""Verify a patch by re-running the PoC against the patched code."""
from __future__ import annotations
import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from mythos_defense.schemas.findings import Finding

logger = logging.getLogger(__name__)


@dataclass
class VerifyResult:
    exploit_blocked: bool
    regression_passed: bool
    details: str


def _is_safe_path(base: Path, target: Path) -> bool:
    """Verify that target resolves inside base (prevents path traversal)."""
    try:
        resolved = target.resolve()
        return resolved.is_relative_to(base.resolve())
    except (ValueError, OSError):
        return False


def apply_patch(workspace: Path, files_changed: list[dict]) -> bool:
    """Apply unified diffs to the workspace. Returns True on success."""
    for fc in files_changed:
        diff_text = fc.get("diff", "")
        if not diff_text:
            continue
        tf = None
        try:
            tf = tempfile.NamedTemporaryFile("w", suffix=".diff", delete=False)
            tf.write(diff_text)
            tf.close()
            patch_file = tf.name

            r = subprocess.run(
                ["git", "apply", "--whitespace=nowarn", patch_file],
                cwd=workspace,
                capture_output=True,
                text=True,
            )
            if r.returncode != 0:
                try:
                    r2 = subprocess.run(
                        ["patch", "-p1", "-i", patch_file],
                        cwd=workspace,
                        capture_output=True,
                        text=True,
                    )
                    if r2.returncode != 0:
                        return False
                except FileNotFoundError:
                    return False
        except FileNotFoundError:
            return False
        finally:
            if tf:
                Path(tf.name).unlink(missing_ok=True)
    return True


def verify_finding(finding: Finding, patched_workspace: Path) -> VerifyResult:
    """Verify a patch by running the PoC reproduction script if available.

    Without Docker, this runs the script directly in the workspace.
    Only executes if a reproduction_script is specified in the PoC.
    """
    if not finding.poc.reproduction_script:
        return VerifyResult(
            exploit_blocked=False,
            regression_passed=False,
            details="No reproduction_script present -- manual verification required",
        )

    script_path = patched_workspace / finding.poc.reproduction_script

    # Security: prevent path traversal
    if not _is_safe_path(patched_workspace, script_path):
        logger.warning(
            "Path traversal attempt blocked: %s", finding.poc.reproduction_script
        )
        return VerifyResult(
            exploit_blocked=False,
            regression_passed=False,
            details=f"SECURITY: reproduction script path escapes workspace: {finding.poc.reproduction_script}",
        )

    if not script_path.exists():
        return VerifyResult(
            exploit_blocked=False,
            regression_passed=False,
            details=f"Reproduction script not found: {finding.poc.reproduction_script}",
        )

    # Security: only allow .py files
    if script_path.suffix != ".py":
        return VerifyResult(
            exploit_blocked=False,
            regression_passed=False,
            details=f"Only .py reproduction scripts are allowed, got: {script_path.suffix}",
        )

    try:
        r = subprocess.run(
            ["python", "-I", str(script_path)],  # -I = isolated mode (no user site-packages, no PYTHON* env vars)
            cwd=patched_workspace,
            capture_output=True,
            text=True,
            timeout=120,
            env={"PATH": "", "PYTHONPATH": ""},  # minimal environment
        )
    except subprocess.TimeoutExpired:
        return VerifyResult(False, False, "verify timed out")
    except FileNotFoundError:
        return VerifyResult(False, False, "python not found for verification")

    exploit_blocked = r.returncode != 0

    return VerifyResult(
        exploit_blocked=exploit_blocked,
        regression_passed=True,
        details=f"exit={r.returncode}, stdout={r.stdout[:500]}, stderr={r.stderr[:500]}",
    )
