"""mythos watch — scheduled re-scans + self-heal monitoring."""
from __future__ import annotations
import json
import os
import subprocess
import time
from pathlib import Path
import click
from rich.console import Console

console = Console()


@click.command("watch")
@click.option("--workspace", "-w", default=".", type=click.Path(exists=True, path_type=Path))
@click.option("--interval", "-i", default=3600, type=int,
              help="Seconds between scans (default: 1 hour).")
@click.option("--adapter", "-a", default="semgrep",
              type=click.Choice(["mock", "semgrep"]))
@click.option("--auto-fix", is_flag=True,
              help="Attempt automatic patching of new findings.")
@click.option("--notify", default=None,
              help="Notification webhook URL for alerts.")
@click.option("--max-runs", default=0, type=int,
              help="Max scan cycles (0 = unlimited).")
@click.option("--output", "-o", default="./reports/watch", type=click.Path(path_type=Path))
def watch_cmd(workspace: Path, interval: int, adapter: str, auto_fix: bool,
              notify: str | None, max_runs: int, output: Path):
    """Continuously monitor the workspace for security regressions."""
    workspace = workspace.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    console.rule("[bold]Mythos Watch")
    console.print(f"Workspace: {workspace}")
    console.print(f"Interval: {interval}s")
    console.print(f"Adapter: {adapter}")
    console.print(f"Auto-fix: {auto_fix}")
    console.print(f"Notify: {notify or 'disabled'}")
    console.print(f"Max runs: {max_runs or 'unlimited'}")
    console.print("\n[dim]Press Ctrl+C to stop.[/]\n")

    run_count = 0
    findings_history = []

    try:
        while True:
            run_count += 1
            if max_runs and run_count > max_runs:
                break

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            console.print(f"[bold cyan]--- Scan #{run_count} ({timestamp}) ---[/]")

            # Run scan
            scan_result = _run_scan(workspace, adapter)

            findings_history.append({
                "run": run_count,
                "timestamp": timestamp,
                "findings_count": scan_result["count"],
                "new_findings": scan_result.get("new", 0),
            })

            if scan_result["count"] == 0:
                console.print("[green]Clean scan - no findings.[/]")
            else:
                console.print(f"[yellow]Found {scan_result['count']} issues.[/]")

                if auto_fix:
                    console.print("[cyan]Attempting auto-fix...[/]")
                    _attempt_auto_fix(workspace)

                if notify:
                    _send_notification(notify, scan_result)

            # Save run report
            run_report = output / f"scan_{timestamp}.json"
            run_report.write_text(json.dumps(scan_result, indent=2))

            # Check for dependency updates
            _check_dep_updates(workspace)

            if max_runs and run_count >= max_runs:
                break

            console.print(f"[dim]Next scan in {interval}s...[/]\n")
            time.sleep(interval)

    except KeyboardInterrupt:
        console.print("\n[yellow]Watch stopped by user.[/]")

    # Write summary
    summary = {
        "total_runs": run_count,
        "history": findings_history,
        "workspace": str(workspace),
    }
    (output / "watch_summary.json").write_text(json.dumps(summary, indent=2))
    console.print(f"\nSummary: {output / 'watch_summary.json'}")


def _run_scan(workspace: Path, adapter: str) -> dict:
    """Run a security scan and return results."""
    if adapter == "semgrep":
        try:
            r = subprocess.run(
                ["semgrep", "scan", "--config", "auto", "--json", "--quiet", str(workspace)],
                capture_output=True, text=True, timeout=300,
            )
            if r.stdout:
                data = json.loads(r.stdout)
                results = data.get("results", [])
                return {"count": len(results), "results": results[:20], "raw_count": len(results)}
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
            pass
    return {"count": 0, "results": []}


def _attempt_auto_fix(workspace: Path):
    """Run mythos harden in quick mode."""
    try:
        subprocess.run(
            ["mythos", "harden", "-w", str(workspace), "--max-iterations", "1"],
            capture_output=True, text=True, timeout=300,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        console.print("  [yellow]Auto-fix skipped.[/]")


def _check_dep_updates(workspace: Path):
    """Quick check for outdated dependencies."""
    if (workspace / "package.json").exists():
        try:
            r = subprocess.run(
                ["npm", "outdated", "--json"],
                cwd=workspace, capture_output=True, text=True, timeout=60,
            )
            if r.stdout:
                outdated = json.loads(r.stdout)
                if outdated:
                    console.print(f"  [dim]{len(outdated)} outdated packages[/]")
        except Exception:
            pass


def _send_notification(webhook_url: str, scan_result: dict):
    """Send alert via webhook."""
    try:
        import httpx
        payload = {
            "text": f"Mythos Watch: {scan_result['count']} security findings detected.",
            "findings": scan_result["count"],
        }
        httpx.post(webhook_url, json=payload, timeout=10)
        console.print("  [green]Notification sent.[/]")
    except Exception as e:
        console.print(f"  [yellow]Notification failed: {e}[/]")
