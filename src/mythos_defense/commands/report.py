"""mythos report — generate weekly security + performance reports."""
from __future__ import annotations
import json
import os
import time
from pathlib import Path
import click
from rich.console import Console
from rich.table import Table
from anthropic import Anthropic

console = Console()

REPORT_SYSTEM_PROMPT = """You are a security and performance analyst. Given scan data, dependency info, and project context, produce a concise weekly report.

Output a single JSON object:

{
  "report_date": "YYYY-MM-DD",
  "executive_summary": "2-3 sentence overview for stakeholders",
  "security_posture": "GREEN|YELLOW|RED",
  "findings_summary": {
    "total_scanned": 0,
    "new_this_week": 0,
    "resolved_this_week": 0,
    "open_critical": 0,
    "open_high": 0
  },
  "dependency_health": {
    "total_deps": 0,
    "outdated": 0,
    "vulnerable": 0,
    "recommendation": "..."
  },
  "performance_notes": ["..."],
  "action_items": [
    {"priority": "P0|P1|P2", "action": "...", "owner": "human|automated"}
  ],
  "trend": "improving|stable|degrading"
}
"""


@click.command("report")
@click.option("--workspace", "-w", default=".", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", default="./reports", type=click.Path(path_type=Path))
@click.option("--format", "report_format", default="json",
              type=click.Choice(["json", "markdown", "both"]))
@click.option("--period", default="week", type=click.Choice(["day", "week", "month"]))
@click.option("--ai-summary", is_flag=True, default=True,
              help="Generate AI-powered executive summary.")
def report_cmd(workspace: Path, output: Path, report_format: str, period: str, ai_summary: bool):
    """Generate a security and health report for the project."""
    workspace = workspace.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    console.rule("[bold]Mythos Report")
    console.print(f"Workspace: {workspace}")
    console.print(f"Period: {period}")
    console.print(f"Format: {report_format}")

    # Gather data
    console.print("\n[bold cyan]Gathering data...[/]")
    scan_data = _gather_scan_history(workspace)
    dep_data = _gather_dependency_info(workspace)
    workflow_data = _gather_workflow_history(workspace)

    # AI summary
    report = None
    if ai_summary and os.getenv("ANTHROPIC_API_KEY"):
        console.print("[bold cyan]Generating AI summary...[/]")
        report = _generate_ai_report(scan_data, dep_data, workflow_data)

    if not report:
        report = _build_basic_report(scan_data, dep_data, workflow_data)

    # Display
    _display_report(report)

    # Save
    timestamp = time.strftime("%Y%m%d")
    if report_format in ("json", "both"):
        json_path = output / f"report_{timestamp}.json"
        json_path.write_text(json.dumps(report, indent=2))
        console.print(f"\n[bold]JSON report:[/] {json_path}")

    if report_format in ("markdown", "both"):
        md_path = output / f"report_{timestamp}.md"
        md_path.write_text(_report_to_markdown(report))
        console.print(f"[bold]Markdown report:[/] {md_path}")


def _gather_scan_history(workspace: Path) -> dict:
    """Collect recent scan results."""
    reports_dir = workspace / "reports" / "watch"
    scans = []
    if reports_dir.exists():
        for f in sorted(reports_dir.glob("scan_*.json"))[-7:]:
            try:
                scans.append(json.loads(f.read_text()))
            except json.JSONDecodeError:
                pass

    workflows_dir = workspace / "workflows"
    workflow_reports = []
    if workflows_dir.exists():
        for d in sorted(workflows_dir.iterdir())[-5:]:
            report_file = d / "report.json"
            if report_file.exists():
                try:
                    workflow_reports.append(json.loads(report_file.read_text()))
                except json.JSONDecodeError:
                    pass

    return {"scans": scans, "workflows": workflow_reports}


def _gather_dependency_info(workspace: Path) -> dict:
    """Collect dependency health info."""
    pkg = workspace / "package.json"
    if pkg.exists():
        data = json.loads(pkg.read_text())
        deps = data.get("dependencies", {})
        dev_deps = data.get("devDependencies", {})
        return {
            "total": len(deps) + len(dev_deps),
            "direct": len(deps),
            "dev": len(dev_deps),
        }
    return {"total": 0, "direct": 0, "dev": 0}


def _gather_workflow_history(workspace: Path) -> dict:
    """Collect workflow execution history."""
    workflows_dir = workspace / "workflows"
    if not workflows_dir.exists():
        return {"total_runs": 0, "converged": 0, "failed": 0}

    total = converged = failed = 0
    for d in workflows_dir.iterdir():
        if d.is_dir():
            report = d / "report.json"
            if report.exists():
                try:
                    data = json.loads(report.read_text())
                    total += 1
                    if data.get("status") == "CONVERGED":
                        converged += 1
                    else:
                        failed += 1
                except json.JSONDecodeError:
                    pass

    return {"total_runs": total, "converged": converged, "failed": failed}


def _generate_ai_report(scan_data: dict, dep_data: dict, workflow_data: dict) -> dict | None:
    """Use Claude to generate an intelligent report."""
    try:
        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        context = json.dumps({
            "scan_history": scan_data,
            "dependencies": dep_data,
            "workflows": workflow_data,
        }, indent=2, default=str)[:20000]

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
            system=REPORT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"Generate the report.\n\n{context}"}],
        )
        output = response.content[0].text.strip()
        if output.startswith("```"):
            output = output.split("```")[1]
            if output.startswith("json"):
                output = output[4:]
        return json.loads(output.strip())
    except Exception:
        return None


def _build_basic_report(scan_data: dict, dep_data: dict, workflow_data: dict) -> dict:
    """Build a report without AI."""
    total_findings = sum(s.get("count", 0) for s in scan_data.get("scans", []))
    return {
        "report_date": time.strftime("%Y-%m-%d"),
        "executive_summary": f"Reviewed {len(scan_data.get('scans', []))} scans. {total_findings} total findings.",
        "security_posture": "GREEN" if total_findings == 0 else "YELLOW" if total_findings < 5 else "RED",
        "findings_summary": {
            "total_scanned": len(scan_data.get("scans", [])),
            "new_this_week": total_findings,
            "resolved_this_week": workflow_data.get("converged", 0),
            "open_critical": 0,
            "open_high": 0,
        },
        "dependency_health": {
            "total_deps": dep_data.get("total", 0),
            "outdated": 0,
            "vulnerable": 0,
            "recommendation": "Run mythos audit for full analysis.",
        },
        "action_items": [],
        "trend": "stable",
    }


def _display_report(report: dict):
    """Display report in the console."""
    posture = report.get("security_posture", "UNKNOWN")
    color = {"GREEN": "green", "YELLOW": "yellow", "RED": "red"}.get(posture, "white")

    console.print(f"\n[bold]Security Posture:[/] [{color}]{posture}[/]")
    console.print(f"[dim]{report.get('executive_summary', '')}[/]")

    if report.get("action_items"):
        console.print("\n[bold]Action Items:[/]")
        for item in report["action_items"]:
            console.print(f"  [{item.get('priority', '?')}] {item.get('action', '')}")


def _report_to_markdown(report: dict) -> str:
    """Convert report to markdown."""
    lines = [
        f"# Security Report — {report.get('report_date', 'Unknown')}",
        "",
        f"**Posture:** {report.get('security_posture', 'UNKNOWN')}",
        "",
        f"## Summary",
        "",
        report.get("executive_summary", ""),
        "",
        "## Findings",
        "",
    ]
    fs = report.get("findings_summary", {})
    lines.append(f"- Scans completed: {fs.get('total_scanned', 0)}")
    lines.append(f"- New findings: {fs.get('new_this_week', 0)}")
    lines.append(f"- Resolved: {fs.get('resolved_this_week', 0)}")
    lines.append("")

    if report.get("action_items"):
        lines.append("## Action Items")
        lines.append("")
        for item in report["action_items"]:
            lines.append(f"- **{item.get('priority', '?')}**: {item.get('action', '')}")

    return "\n".join(lines) + "\n"
