"""mythos CLI."""
from __future__ import annotations
import os
import sys
import uuid
from pathlib import Path
import click
from dotenv import load_dotenv
from rich.console import Console

from mythos_defense.adapters.mock import MockAdapter
from mythos_defense.adapters.semgrep import SemgrepAdapter
from mythos_defense.orchestrator.workflow import Orchestrator, WorkflowConfig
from mythos_defense.orchestrator.budget import Budget

load_dotenv(override=True)
console = Console()


@click.group()
def main():
    """Mythos Defense Platform — autonomous premium web security."""
    pass


# --- Original V0 commands ---

@main.command()
@click.option("--workspace", "-w", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--brief", "-b", required=True, help="Path to project brief markdown, or inline text.")
@click.option("--adapter", "-a", default="mock", type=click.Choice(["mock", "semgrep"]))
@click.option("--output", "-o", default="./workflows", type=click.Path(path_type=Path))
@click.option("--max-iterations", default=3, type=int)
@click.option("--max-tokens", default=500_000, type=int)
@click.option("--fixtures", default="tests/fixtures/findings", type=click.Path(path_type=Path),
              help="Fixtures dir for mock adapter")
def assess(workspace, brief, adapter, output, max_iterations, max_tokens, fixtures):
    """Run a full security assessment workflow."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        console.print("[red]ANTHROPIC_API_KEY not set. Set it in .env or environment.[/]")
        sys.exit(1)

    brief_path = Path(brief)
    if brief_path.exists():
        brief_text = brief_path.read_text()
    else:
        brief_text = brief

    if adapter == "mock":
        rt_adapter = MockAdapter(fixtures_dir=fixtures)
    elif adapter == "semgrep":
        rt_adapter = SemgrepAdapter()
    else:
        console.print(f"[red]Unknown adapter: {adapter}[/]")
        sys.exit(1)

    workflow_id = f"wf-{uuid.uuid4().hex[:8]}"
    cfg = WorkflowConfig(
        workflow_id=workflow_id,
        workspace=workspace.absolute(),
        brief=brief_text,
        output_dir=output / workflow_id,
        budget=Budget(max_iterations=max_iterations, max_tokens=max_tokens),
    )

    console.rule(f"[bold]Workflow {workflow_id}")
    console.print(f"Workspace: {cfg.workspace}")
    console.print(f"Adapter: {adapter}")
    console.print(f"Output: {cfg.output_dir}")

    orchestrator = Orchestrator(red_team_adapter=rt_adapter)
    result = orchestrator.run(cfg)

    console.rule(f"[bold]Done -- {result.status}")
    console.print(f"Duration: {result.duration_seconds:.1f}s")
    console.print(f"Patches applied: {len(result.patches_applied)}")
    console.print(f"Unresolved: {len(result.unresolved_findings)}")
    console.print(f"Report: {cfg.output_dir / 'report.json'}")

    if result.unresolved_findings:
        sys.exit(2)


@main.command("threat-model")
@click.option("--brief", "-b", required=True)
def threat_model(brief):
    """Just produce a threat model -- no scanning, no patches."""
    from mythos_defense.agents.architect import ArchitectAgent
    import json
    brief_path = Path(brief)
    text = brief_path.read_text() if brief_path.exists() else brief
    agent = ArchitectAgent()
    result = agent.run(text)
    click.echo(json.dumps(result.structured, indent=2))


@main.command()
def doctor():
    """Check that adapters and tools are available."""
    checks = [
        ("ANTHROPIC_API_KEY set", bool(os.getenv("ANTHROPIC_API_KEY"))),
        ("semgrep installed", SemgrepAdapter().healthcheck()),
    ]
    for name, ok in checks:
        symbol = "[green]PASS[/]" if ok else "[red]FAIL[/]"
        console.print(f"{symbol} {name}")


# --- New commands ---

from mythos_defense.commands.init import init_cmd
from mythos_defense.commands.new import new_cmd
from mythos_defense.commands.plan import plan_cmd
from mythos_defense.commands.build import build_cmd
from mythos_defense.commands.review import review_cmd
from mythos_defense.commands.harden import harden_cmd
from mythos_defense.commands.audit import audit_cmd
from mythos_defense.commands.sandbox import sandbox_cmd
from mythos_defense.commands.deploy import deploy_cmd
from mythos_defense.commands.watch import watch_cmd
from mythos_defense.commands.report import report_cmd

main.add_command(init_cmd)
main.add_command(new_cmd)
main.add_command(plan_cmd)
main.add_command(build_cmd)
main.add_command(review_cmd)
main.add_command(harden_cmd)
main.add_command(audit_cmd)
main.add_command(sandbox_cmd)
main.add_command(deploy_cmd)
main.add_command(watch_cmd)
main.add_command(report_cmd)


if __name__ == "__main__":
    main()
