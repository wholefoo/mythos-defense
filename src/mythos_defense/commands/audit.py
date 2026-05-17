"""mythos audit — SBOM generation + dependency vulnerability audit."""
from __future__ import annotations
import json
import logging
import os
import subprocess
import time
from pathlib import Path
import click
from rich.console import Console
from rich.table import Table
from anthropic import Anthropic
from mythos_defense.utils import sev_color

logger = logging.getLogger(__name__)

console = Console()


@click.command("audit")
@click.option("--workspace", "-w", default=".", type=click.Path(exists=True, path_type=Path),
              help="Project workspace.")
@click.option("--sbom", "sbom_format", default="cyclonedx",
              type=click.Choice(["cyclonedx", "spdx", "json"]),
              help="SBOM output format.")
@click.option("--deps", "dep_managers", default="npm",
              help="Comma-separated dependency managers: npm,pnpm,pip.")
@click.option("--output", "-o", default="./reports", type=click.Path(path_type=Path),
              help="Output directory for reports.")
@click.option("--fix", is_flag=True, help="Attempt to auto-fix vulnerabilities.")
def audit_cmd(workspace: Path, sbom_format: str, dep_managers: str, output: Path, fix: bool):
    """Generate SBOM and audit dependencies for vulnerabilities."""
    workspace = workspace.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    managers = [m.strip() for m in dep_managers.split(",")]

    console.rule("[bold]Mythos Audit")
    console.print(f"Workspace: {workspace}")
    console.print(f"Package managers: {', '.join(managers)}")
    console.print(f"SBOM format: {sbom_format}")

    all_vulns = []
    dep_count = 0

    for manager in managers:
        console.print(f"\n[bold cyan]Auditing: {manager}[/]")

        if manager == "npm":
            vulns, count = _audit_npm(workspace, output, sbom_format, fix)
        elif manager == "pnpm":
            vulns, count = _audit_pnpm(workspace, output, fix)
        elif manager == "pip":
            vulns, count = _audit_pip(workspace, output, fix)
        else:
            console.print(f"  [yellow]Unknown manager: {manager}[/]")
            continue

        all_vulns.extend(vulns)
        dep_count += count

    # Generate SBOM
    console.print(f"\n[bold cyan]Generating SBOM ({sbom_format})...[/]")
    sbom_path = _generate_sbom(workspace, output, sbom_format, managers)
    if sbom_path:
        console.print(f"  [green]SBOM written:[/] {sbom_path}")

    # AI analysis if we have vulns and an API key
    ai_analysis = None
    if all_vulns and os.getenv("ANTHROPIC_API_KEY"):
        console.print("\n[bold cyan]AI supply chain analysis...[/]")
        from mythos_defense.agents.supply_chain import SupplyChainAgent
        try:
            agent = SupplyChainAgent()
            result = agent.run(workspace)
            ai_analysis = result.structured
        except Exception as e:
            console.print(f"  [yellow]AI analysis skipped: {e}[/]")

    # Summary table
    console.print("\n")
    table = Table(title="Audit Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value")
    table.add_row("Total dependencies", str(dep_count))
    table.add_row("Vulnerabilities found", str(len(all_vulns)))
    table.add_row("Critical", str(sum(1 for v in all_vulns if v.get("severity") == "critical")))
    table.add_row("High", str(sum(1 for v in all_vulns if v.get("severity") == "high")))
    table.add_row("Medium", str(sum(1 for v in all_vulns if v.get("severity") == "moderate")))
    table.add_row("Low", str(sum(1 for v in all_vulns if v.get("severity") == "low")))
    console.print(table)

    # Write full report
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "workspace": str(workspace),
        "dependency_count": dep_count,
        "vulnerabilities": all_vulns,
        "sbom_path": str(sbom_path) if sbom_path else None,
        "ai_analysis": ai_analysis,
    }
    report_path = output / "audit_report.json"
    report_path.write_text(json.dumps(report, indent=2))
    console.print(f"\n[bold]Report:[/] {report_path}")

    if any(v.get("severity") in ("critical", "high") for v in all_vulns):
        console.print("\n[bold red]Critical/high vulnerabilities found. Review required.[/]")
        raise SystemExit(2)
    else:
        console.print("\n[bold green]No critical vulnerabilities.[/]")
        console.print("Next: [bold]mythos deploy[/]")


def _audit_npm(workspace: Path, output: Path, sbom_format: str, fix: bool) -> tuple[list, int]:
    """Run npm audit and return (vulnerabilities, dependency_count)."""
    if not (workspace / "package.json").exists():
        console.print("  [dim]No package.json found[/]")
        return [], 0

    # Get dep count
    pkg = json.loads((workspace / "package.json").read_text())
    dep_count = len(pkg.get("dependencies", {})) + len(pkg.get("devDependencies", {}))

    # Run audit
    try:
        r = subprocess.run(
            ["npm", "audit", "--json"],
            cwd=workspace, capture_output=True, text=True, timeout=120,
        )
        audit_data = json.loads(r.stdout) if r.stdout else {}
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        logger.warning("npm audit failed: %s", e)
        console.print("  [yellow]npm audit failed[/]")
        return [], dep_count

    vulns = []
    for name, advisory in audit_data.get("vulnerabilities", {}).items():
        vulns.append({
            "package": name,
            "severity": advisory.get("severity", "unknown"),
            "via": [str(v) if isinstance(v, str) else v.get("title", "") for v in advisory.get("via", [])],
            "fix_available": advisory.get("fixAvailable", False),
        })
        sev = advisory.get("severity", "?")
        console.print(f"  [{sev_color(sev)}]{sev}[/] {name}")

    # Auto-fix
    if fix and vulns:
        console.print("  [cyan]Running npm audit fix...[/]")
        subprocess.run(["npm", "audit", "fix"], cwd=workspace,
                       capture_output=True, text=True, timeout=120)

    # Save raw audit
    (output / "npm_audit.json").write_text(json.dumps(audit_data, indent=2))
    return vulns, dep_count


def _audit_pnpm(workspace: Path, output: Path, fix: bool) -> tuple[list, int]:
    """Run pnpm audit."""
    if not (workspace / "pnpm-lock.yaml").exists():
        return [], 0
    try:
        r = subprocess.run(
            ["pnpm", "audit", "--json"],
            cwd=workspace, capture_output=True, text=True, timeout=120,
        )
        data = json.loads(r.stdout) if r.stdout else {}
        vulns = [{"package": a.get("module_name"), "severity": a.get("severity")}
                 for a in data.get("advisories", {}).values()]
        return vulns, data.get("metadata", {}).get("totalDependencies", 0)
    except Exception:
        return [], 0


def _audit_pip(workspace: Path, output: Path, fix: bool) -> tuple[list, int]:
    """Run pip-audit."""
    try:
        r = subprocess.run(
            ["pip-audit", "--format", "json", "--requirement",
             str(workspace / "requirements.txt")] if (workspace / "requirements.txt").exists()
            else ["pip-audit", "--format", "json"],
            cwd=workspace, capture_output=True, text=True, timeout=120,
        )
        data = json.loads(r.stdout) if r.stdout else []
        vulns = [{"package": v.get("name"), "severity": "high",
                  "via": v.get("vulnerabilities", [])} for v in data if v.get("vulnerabilities")]
        return vulns, len(data)
    except Exception:
        return [], 0


def _generate_sbom(workspace: Path, output: Path, fmt: str, managers: list) -> Path | None:
    """Generate SBOM using available tools."""
    if "npm" in managers and (workspace / "package.json").exists():
        sbom_path = output / f"sbom.{fmt}.json"
        try:
            if fmt == "cyclonedx":
                r = subprocess.run(
                    ["npx", "@cyclonedx/cyclonedx-npm", "--output-file", str(sbom_path)],
                    cwd=workspace, capture_output=True, text=True, timeout=120,
                )
                if r.returncode == 0:
                    return sbom_path
            # Fallback: generate basic SBOM from package-lock
            lock_path = workspace / "package-lock.json"
            if lock_path.exists():
                lock_data = json.loads(lock_path.read_text())
                packages = lock_data.get("packages", lock_data.get("dependencies", {}))
                sbom = {
                    "bomFormat": fmt,
                    "specVersion": "1.4",
                    "components": [
                        {"type": "library", "name": k.split("node_modules/")[-1],
                         "version": v.get("version", "")}
                        for k, v in packages.items() if k
                    ],
                }
                sbom_path.write_text(json.dumps(sbom, indent=2))
                return sbom_path
        except Exception:
            pass
    return None


