"""mythos sandbox — isolated runtime environment for testing."""
from __future__ import annotations
import json
import os
import subprocess
import signal
import time
from pathlib import Path
import click
from rich.console import Console

console = Console()


@click.group("sandbox")
def sandbox_cmd():
    """Manage isolated sandbox environments for testing."""
    pass


@sandbox_cmd.command("up")
@click.option("--workspace", "-w", default=".", type=click.Path(exists=True, path_type=Path))
@click.option("--port", "-p", default=3000, type=int, help="Port to expose.")
@click.option("--isolate", default="process",
              type=click.Choice(["process", "gvisor"]),
              help="Isolation level.")
@click.option("--env-file", default=".env.local", type=click.Path(path_type=Path),
              help="Environment file to load.")
def sandbox_up(workspace: Path, port: int, isolate: str, env_file: Path):
    """Start the application in an isolated sandbox."""
    workspace = workspace.resolve()
    console.rule("[bold]Mythos Sandbox Up")
    console.print(f"Workspace: {workspace}")
    console.print(f"Port: {port}")
    console.print(f"Isolation: {isolate}")

    # Determine start command
    start_cmd = _detect_start_command(workspace)
    if not start_cmd:
        console.print("[red]Cannot determine start command. Add a 'dev' script to package.json.[/]")
        raise SystemExit(1)

    console.print(f"Start command: {' '.join(start_cmd)}")

    # Build environment
    env = os.environ.copy()
    env["PORT"] = str(port)
    env["NODE_ENV"] = "development"

    env_path = workspace / env_file
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()

    if isolate == "gvisor":
        console.print("[yellow]gVisor isolation requires Linux + runsc. Falling back to process.[/]")

    # Start process
    console.print(f"\n[bold cyan]Starting sandbox on port {port}...[/]")
    proc = subprocess.Popen(
        start_cmd,
        cwd=workspace,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # Write PID file
    pid_file = workspace / ".sandbox.pid"
    pid_file.write_text(json.dumps({"pid": proc.pid, "port": port, "isolate": isolate}))

    # Wait for server to be ready
    ready = _wait_for_ready(f"http://localhost:{port}", timeout=30)
    if ready:
        console.print(f"[bold green]Sandbox running at http://localhost:{port}[/]")
        console.print(f"  PID: {proc.pid}")
        console.print(f"  Stop with: [bold]mythos sandbox down[/]")
    else:
        console.print("[yellow]Server started but may not be fully ready yet.[/]")
        console.print(f"  PID: {proc.pid}")


@sandbox_cmd.command("down")
@click.option("--workspace", "-w", default=".", type=click.Path(exists=True, path_type=Path))
def sandbox_down(workspace: Path):
    """Stop the running sandbox."""
    workspace = workspace.resolve()
    pid_file = workspace / ".sandbox.pid"

    if not pid_file.exists():
        console.print("[yellow]No sandbox running (no .sandbox.pid found).[/]")
        return

    data = json.loads(pid_file.read_text())
    pid = data["pid"]

    console.print(f"Stopping sandbox (PID {pid})...")
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/PID", str(pid), "/T"],
                           capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
        console.print("[green]Sandbox stopped.[/]")
    except (ProcessLookupError, OSError) as e:
        console.print(f"[yellow]Process already stopped: {e}[/]")

    pid_file.unlink(missing_ok=True)


@sandbox_cmd.command("smoke")
@click.option("--workspace", "-w", default=".", type=click.Path(exists=True, path_type=Path))
@click.option("--e2e", "test_runner", default="playwright",
              type=click.Choice(["playwright", "cypress", "jest"]),
              help="E2E test runner to use.")
@click.option("--url", default="http://localhost:3000")
def sandbox_smoke(workspace: Path, test_runner: str, url: str):
    """Run smoke/E2E tests against the running sandbox."""
    workspace = workspace.resolve()
    console.rule("[bold]Mythos Sandbox Smoke Test")
    console.print(f"Runner: {test_runner}")
    console.print(f"URL: {url}")

    # Check server is up
    if not _wait_for_ready(url, timeout=5):
        console.print("[red]Sandbox not running. Start with: mythos sandbox up[/]")
        raise SystemExit(1)

    if test_runner == "playwright":
        cmd = ["npx", "playwright", "test", "--reporter=list"]
    elif test_runner == "cypress":
        cmd = ["npx", "cypress", "run", "--config", f"baseUrl={url}"]
    elif test_runner == "jest":
        cmd = ["npx", "jest", "--testPathPattern", "e2e"]

    console.print(f"\n[bold cyan]Running: {' '.join(cmd)}[/]\n")
    r = subprocess.run(cmd, cwd=workspace, timeout=300)

    if r.returncode == 0:
        console.print("\n[bold green]All smoke tests passed.[/]")
        console.print("Next: [bold]mythos deploy[/]")
    else:
        console.print(f"\n[bold red]Tests failed (exit {r.returncode}).[/]")
        raise SystemExit(r.returncode)


@sandbox_cmd.command("status")
@click.option("--workspace", "-w", default=".", type=click.Path(exists=True, path_type=Path))
def sandbox_status(workspace: Path):
    """Check sandbox status."""
    workspace = workspace.resolve()
    pid_file = workspace / ".sandbox.pid"

    if not pid_file.exists():
        console.print("[dim]No sandbox running.[/]")
        return

    data = json.loads(pid_file.read_text())
    pid = data["pid"]
    port = data.get("port", "?")

    running = _is_process_running(pid)
    if running:
        console.print(f"[green]Sandbox running[/] PID={pid} port={port}")
    else:
        console.print(f"[yellow]Sandbox PID file exists but process {pid} is not running.[/]")
        pid_file.unlink(missing_ok=True)


def _detect_start_command(workspace: Path) -> list[str] | None:
    pkg = workspace / "package.json"
    if pkg.exists():
        data = json.loads(pkg.read_text())
        scripts = data.get("scripts", {})
        if "dev" in scripts:
            return ["npm", "run", "dev"]
        if "start" in scripts:
            return ["npm", "start"]

    if (workspace / "manage.py").exists():
        return ["python", "manage.py", "runserver"]

    if (workspace / "app.py").exists():
        return ["python", "app.py"]

    return None


def _wait_for_ready(url: str, timeout: int = 30) -> bool:
    import httpx
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=2, follow_redirects=True)
            if r.status_code < 500:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def _is_process_running(pid: int) -> bool:
    try:
        if os.name == "nt":
            r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                               capture_output=True, text=True)
            return str(pid) in r.stdout
        else:
            os.kill(pid, 0)
            return True
    except (OSError, ProcessLookupError):
        return False
