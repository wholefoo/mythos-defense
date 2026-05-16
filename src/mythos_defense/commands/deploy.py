"""mythos deploy — multi-platform deployment with comparison matrix."""
from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path
import click
from rich.console import Console
from rich.table import Table

console = Console()

PLATFORMS = {
    "vercel": {
        "cost_free_tier": "$0/mo (hobby)",
        "cost_pro": "$20/mo/member",
        "features": ["Edge functions", "Serverless", "Preview deploys", "Analytics"],
        "latency": "~50ms (edge)",
        "ai_fit": "Excellent (AI SDK, streaming)",
        "deploy_cmd": ["npx", "vercel", "--prod", "--yes"],
        "build_cmd": ["npm", "run", "build"],
    },
    "netlify": {
        "cost_free_tier": "$0/mo (starter)",
        "cost_pro": "$19/mo/member",
        "features": ["Edge functions", "Forms", "Identity", "Split testing"],
        "latency": "~60ms (CDN)",
        "ai_fit": "Good (serverless functions)",
        "deploy_cmd": ["npx", "netlify", "deploy", "--prod"],
        "build_cmd": ["npm", "run", "build"],
    },
    "github-pages": {
        "cost_free_tier": "$0 (public repos)",
        "cost_pro": "$4/mo (Pro for private)",
        "features": ["Static only", "Custom domains", "HTTPS"],
        "latency": "~80ms (CDN)",
        "ai_fit": "Poor (no server-side)",
        "deploy_cmd": ["npm", "run", "build"],
        "build_cmd": ["npm", "run", "build"],
    },
    "aws": {
        "cost_free_tier": "~$5-50/mo (varies)",
        "cost_pro": "Pay per use",
        "features": ["Full IaaS", "Lambda", "CloudFront", "S3"],
        "latency": "~40ms (CloudFront)",
        "ai_fit": "Excellent (Bedrock, SageMaker)",
        "deploy_cmd": ["npx", "sst", "deploy", "--stage", "prod"],
        "build_cmd": ["npm", "run", "build"],
    },
    "modal": {
        "cost_free_tier": "$30 free credits/mo",
        "cost_pro": "Pay per compute-second",
        "features": ["GPU access", "Scheduled jobs", "Web endpoints", "Volumes"],
        "latency": "~100ms (cold start)",
        "ai_fit": "Excellent (GPU, Python native)",
        "deploy_cmd": ["modal", "deploy"],
        "build_cmd": None,
    },
}


@click.command("deploy")
@click.option("--workspace", "-w", default=".", type=click.Path(exists=True, path_type=Path))
@click.option("--compare", default=None,
              help="Comma-separated platforms to compare (shows matrix without deploying).")
@click.option("--show", default="cost,features,latency,ai-fit",
              help="Columns to show in comparison.")
@click.option("--target", "-t", default=None,
              type=click.Choice(list(PLATFORMS.keys())),
              help="Deploy to this platform.")
@click.option("--dry-run", is_flag=True, help="Show deploy command without executing.")
def deploy_cmd(workspace: Path, compare: str | None, show: str, target: str | None, dry_run: bool):
    """Deploy the project or compare hosting platforms."""
    workspace = workspace.resolve()

    console.rule("[bold]Mythos Deploy")

    # Comparison mode
    if compare:
        platforms = [p.strip() for p in compare.split(",")]
        _show_comparison(platforms, show)
        if not target:
            console.print("\nTo deploy: [bold]mythos deploy --target <platform>[/]")
            return

    # Deploy mode
    if not target:
        console.print("Specify --target or --compare. Available platforms:")
        for name in PLATFORMS:
            console.print(f"  - {name}")
        return

    if target not in PLATFORMS:
        console.print(f"[red]Unknown platform: {target}[/]")
        raise SystemExit(1)

    platform = PLATFORMS[target]
    console.print(f"Target: [bold]{target}[/]")
    console.print(f"Workspace: {workspace}")

    # Build step
    if platform.get("build_cmd"):
        console.print(f"\n[bold cyan]Building...[/]")
        build_cmd_list = platform["build_cmd"]
        if dry_run:
            console.print(f"  [dim]Would run: {' '.join(build_cmd_list)}[/]")
        else:
            r = subprocess.run(build_cmd_list, cwd=workspace, timeout=300)
            if r.returncode != 0:
                console.print("[red]Build failed.[/]")
                raise SystemExit(1)
            console.print("[green]Build successful.[/]")

    # Deploy step
    console.print(f"\n[bold cyan]Deploying to {target}...[/]")
    deploy_cmd_list = platform["deploy_cmd"]

    if dry_run:
        console.print(f"  [dim]Would run: {' '.join(deploy_cmd_list)}[/]")
        console.print("\n[bold]Dry run complete.[/] Remove --dry-run to deploy for real.")
        return

    # Check prerequisites
    if target == "vercel" and not _cmd_exists("vercel"):
        console.print("[yellow]Installing Vercel CLI...[/]")
        subprocess.run(["npm", "install", "-g", "vercel"], capture_output=True, timeout=60)

    if target == "netlify" and not _cmd_exists("netlify"):
        console.print("[yellow]Installing Netlify CLI...[/]")
        subprocess.run(["npm", "install", "-g", "netlify-cli"], capture_output=True, timeout=60)

    r = subprocess.run(deploy_cmd_list, cwd=workspace, timeout=600)
    if r.returncode == 0:
        console.print(f"\n[bold green]Deployed to {target} successfully.[/]")
        console.print("Next: [bold]mythos watch[/]")
    else:
        console.print(f"\n[bold red]Deploy failed (exit {r.returncode}).[/]")
        raise SystemExit(r.returncode)


def _show_comparison(platforms: list[str], show_cols: str):
    """Display platform comparison table."""
    cols = [c.strip() for c in show_cols.split(",")]

    table = Table(title="Platform Comparison")
    table.add_column("Platform", style="bold cyan")

    col_map = {
        "cost": ("Cost (Free / Pro)", lambda p: f"{p['cost_free_tier']} / {p['cost_pro']}"),
        "features": ("Features", lambda p: ", ".join(p["features"][:3])),
        "latency": ("Latency", lambda p: p["latency"]),
        "ai-fit": ("AI Fit", lambda p: p["ai_fit"]),
    }

    for col in cols:
        if col in col_map:
            table.add_column(col_map[col][0])

    for name in platforms:
        if name not in PLATFORMS:
            continue
        p = PLATFORMS[name]
        row = [name]
        for col in cols:
            if col in col_map:
                row.append(col_map[col][1](p))
        table.add_row(*row)

    console.print(table)


def _cmd_exists(cmd: str) -> bool:
    try:
        subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
