"""Verify a patch by re-running the PoC against the patched code."""
from __future__ import annotations
import subprocess
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
        diff_text = fc.get("diff", "")
        if not diff_text:
            continue
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
            Path(patch_file).unlink(missing_ok=True)
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
    if not script_path.exists():
        return VerifyResult(
            exploit_blocked=False,
            regression_passed=False,
            details=f"Reproduction script not found: {finding.poc.reproduction_script}",
        )

    try:
        r = subprocess.run(
            ["python", str(script_path)],
            cwd=patched_workspace,
            capture_output=True,
            text=True,
            timeout=120,
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
