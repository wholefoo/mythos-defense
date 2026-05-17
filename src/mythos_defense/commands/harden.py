"""mythos harden — red/blue adversarial hardening loop."""
from __future__ import annotations
import json
import os
from pathlib import Path
import click
from rich.console import Console

from mythos_defense.adapters.mock import MockAdapter
from mythos_defense.adapters.semgrep import SemgrepAdapter
from mythos_defense.orchestrator.workflow import Orchestrator, WorkflowConfig
from mythos_defense.orchestrator.budget import Budget

console = Console()

VULN_CLASSES = [
    "authn", "injection", "access", "crypto",
    "toctou", "api", "supply-chain", "config",
]


@click.command("harden")
@click.option("--workspace", "-w", default=".", type=click.Path(exists=True, path_type=Path),
              help="Project workspace to harden.")
@click.option("--brief", "-b", default=None, type=click.Path(path_type=Path),
              help="Project brief for threat modeling.")
@click.option("--classes", "-c", default=",".join(VULN_CLASSES),
              help="Comma-separated vulnerability classes to test.")
@click.option("--red-team", "red_team_adapter", default="semgrep",
              type=click.Choice(["mock", "semgrep"]),
              help="Red team adapter to use.")
@click.option("--max-escalations", default=3, type=int,
              help="Max failed patch attempts before escalating to human.")
@click.option("--max-iterations", default=5, type=int,
              help="Max red/blue loop iterations.")
@click.option("--max-tokens", default=1_000_000, type=int,
              help="Token budget for the full workflow.")
@click.option("--output", "-o", default="./workflows", type=click.Path(path_type=Path))
def harden_cmd(workspace: Path, brief: Path | None, classes: str,
               red_team_adapter: str, max_escalations: int,
               max_iterations: int, max_tokens: int, output: Path):
    """Run adversarial red/blue hardening loop against the workspace."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[red]ANTHROPIC_API_KEY not set.[/]")
        raise SystemExit(1)

    workspace = workspace.resolve()
    vuln_classes = [c.strip() for c in classes.split(",")]

    console.rule("[bold]Mythos Harden")
    console.print(f"Workspace: {workspace}")
    console.print(f"Red team: {red_team_adapter}")
    console.print(f"Classes: {', '.join(vuln_classes)}")
    console.print(f"Max iterations: {max_iterations}")
    console.print(f"Max escalations: {max_escalations}")

    # Resolve brief
    if brief and brief.exists():
        brief_text = brief.read_text()
    else:
        brief_text = _infer_brief(workspace)
        console.print("[dim]No brief provided — inferred from workspace.[/]")

    # Select adapter
    if red_team_adapter == "mock":
        fixtures_dir = workspace / "tests" / "fixtures" / "findings"
        if not fixtures_dir.exists():
            fixtures_dir = Path("tests/fixtures/findings")
        adapter = MockAdapter(fixtures_dir=fixtures_dir)
    elif red_team_adapter == "semgrep":
        adapter = SemgrepAdapter(config="auto")
    else:
        console.print(f"[red]Unknown adapter: {red_team_adapter}[/]")
        raise SystemExit(1)

    # Run orchestrator
    import uuid
    workflow_id = f"harden-{uuid.uuid4().hex[:8]}"

    cfg = WorkflowConfig(
        workflow_id=workflow_id,
        workspace=workspace,
        brief=brief_text,
        output_dir=output / workflow_id,
        budget=Budget(
            max_iterations=max_iterations,
            max_tokens=max_tokens,
            max_blue_attempts_per_finding=max_escalations,
        ),
    )

    orchestrator = Orchestrator(red_team_adapter=adapter)
    result = orchestrator.run(cfg)

    # Report
    console.rule(f"[bold]Harden Complete -- {result.status}")
    console.print(f"  Duration: {result.duration_seconds:.1f}s")
    console.print(f"  Patches applied: {len(result.patches_applied)}")
    console.print(f"  Unresolved: {len(result.unresolved_findings)}")

    if result.unresolved_findings:
        console.print("\n[bold yellow]Unresolved findings (escalate to human):[/]")
        for f in result.unresolved_findings:
            console.print(f"  [{f.severity.value}] {f.finding_id}: {f.title}")

    report_path = cfg.output_dir / "report.json"
    console.print(f"\n  Report: {report_path}")

    if result.status == "CONVERGED":
        console.print("\n[bold green]All findings resolved. Workspace hardened.[/]")
        console.print("Next: [bold]mythos audit[/]")
    else:
        raise SystemExit(2)


def _infer_brief(workspace: Path) -> str:
    """Build a minimal brief from package.json or project files."""
    pkg = workspace / "package.json"
    if pkg.exists():
        data = json.loads(pkg.read_text())
        name = data.get("name", "Unknown")
        desc = data.get("description", "A web application")
        deps = list(data.get("dependencies", {}).keys())[:10]
        return f"# {name}\n\n{desc}\n\n## Tech\n- " + "\n- ".join(deps)

    pyproject = workspace / "pyproject.toml"
    if pyproject.exists():
        return f"# Python Project\n\nSee pyproject.toml for details.\n\n{pyproject.read_text()[:2000]}"

    return "# Web Application\n\nA web application requiring security hardening."
