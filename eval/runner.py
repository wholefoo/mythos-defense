"""Minimal evaluation harness — runs workflows against known-vulnerable apps,
compares findings to expected ground truth."""
from __future__ import annotations
import json
import time
from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass
class EvalCase:
    name: str
    repo: str
    expected_classes: list[str]
    brief_path: Path
    adapter: str = "semgrep"


@dataclass
class EvalResult:
    case: str
    detected_classes: set[str]
    expected_classes: set[str]
    recall: float
    precision: float
    duration_seconds: float


CASES = [
    EvalCase(
        name="juice-shop",
        repo="https://github.com/juice-shop/juice-shop",
        expected_classes=["INJECTION_SQL", "XSS_REFLECTED", "AUTH_BYPASS", "IDOR"],
        brief_path=Path("eval/suites/juice_shop_brief.md"),
    ),
    EvalCase(
        name="nodegoat",
        repo="https://github.com/OWASP/NodeGoat",
        expected_classes=["INJECTION_SQL", "XSS_REFLECTED", "CSRF", "CRYPTO_IMPL"],
        brief_path=Path("eval/suites/nodegoat_brief.md"),
    ),
]


def run_case(case: EvalCase, work_root: Path) -> EvalResult:
    repo_dir = work_root / case.name
    if not repo_dir.exists():
        subprocess.run(["git", "clone", "--depth", "1", case.repo, str(repo_dir)], check=True)

    output_dir = work_root / "out" / case.name
    cmd = [
        "mythos", "assess",
        "-w", str(repo_dir),
        "-b", str(case.brief_path),
        "-a", case.adapter,
        "-o", str(output_dir),
        "--max-iterations", "2",
    ]
    t0 = time.time()
    subprocess.run(cmd, check=False)
    duration = time.time() - t0

    workflow_dirs = sorted(output_dir.iterdir()) if output_dir.exists() else []
    if not workflow_dirs:
        return EvalResult(case.name, set(), set(case.expected_classes), 0, 0, duration)
    report = json.loads((workflow_dirs[-1] / "report.json").read_text())

    detected = set()
    for iteration in report.get("iterations", []):
        for f in iteration:
            detected.add(f["vuln_class"])

    expected = set(case.expected_classes)
    recall = len(detected & expected) / len(expected) if expected else 0
    precision = len(detected & expected) / len(detected) if detected else 0

    return EvalResult(case.name, detected, expected, recall, precision, duration)


def main():
    work_root = Path("eval/work")
    work_root.mkdir(parents=True, exist_ok=True)

    print(f"{'CASE':20} {'RECALL':>8} {'PRECISION':>10} {'DURATION':>10}")
    print("-" * 55)

    for case in CASES:
        if not case.brief_path.exists():
            case.brief_path.parent.mkdir(parents=True, exist_ok=True)
            case.brief_path.write_text(f"# {case.name}\n\nKnown-vulnerable application.\n")

        result = run_case(case, work_root)
        print(f"{result.case:20} {result.recall:>7.1%} {result.precision:>9.1%} {result.duration_seconds:>9.1f}s")


if __name__ == "__main__":
    main()
