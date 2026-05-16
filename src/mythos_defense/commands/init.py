"""mythos init — bootstrap workspace, keys, sandbox, and MCP integrations."""
from __future__ import annotations
import json
import os
import subprocess
import shutil
from pathlib import Path
import click
from rich.console import Console
from rich.table import Table

console = Console()

SUPPORTED_SANDBOXES = ["process", "gvisor"]
SUPPORTED_MCPS = ["firecrawl", "nano-banana-2", "relume", "stitch", "spline"]

DEFAULT_DIRS = [
    ".claude",
    "workflows",
    "tools",
    "brand_assets",
    "temporary_screenshots",
    "reports",
]


@click.command("init")
@click.option("--workdir", "-d", default=".", type=click.Path(path_type=Path),
              help="Root working directory for projects.")
@click.option("--claude-key", envvar="ANTHROPIC_API_KEY", default=None,
              help="Anthropic API key (or set ANTHROPIC_API_KEY env var).")
@click.option("--codex-key", envvar="OPENAI_API_KEY", default=None,
              help="OpenAI API key for Codex integration (or set OPENAI_API_KEY).")
@click.option("--sandbox", type=click.Choice(SUPPORTED_SANDBOXES), default="process",
              help="Sandbox runtime: 'process' (local), 'gvisor' (container isolation).")
@click.option("--mcp", "mcp_list", default=None,
              help="Comma-separated MCP integrations to configure.")
def init_cmd(workdir: Path, claude_key: str | None, codex_key: str | None,
             sandbox: str, mcp_list: str | None):
    """Bootstrap the Mythos workspace with keys, directories, and integrations."""
    workdir = workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    console.rule("[bold]Mythos Init")
    console.print(f"Workspace: {workdir}")

    # Create directory structure
    console.print("\n[bold cyan]Creating directory structure...[/]")
    for d in DEFAULT_DIRS:
        (workdir / d).mkdir(parents=True, exist_ok=True)
        console.print(f"  {d}/")

    # Write/update .env
    env_path = workdir / ".env"
    env_vars = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip()

    if claude_key:
        env_vars["ANTHROPIC_API_KEY"] = claude_key
    if codex_key:
        env_vars["OPENAI_API_KEY"] = codex_key
    env_vars.setdefault("WORKFLOW_OUTPUT_DIR", "./workflows")
    env_vars.setdefault("LOG_LEVEL", "INFO")
    env_vars["MYTHOS_SANDBOX"] = sandbox

    env_content = "\n".join(f"{k}={v}" for k, v in env_vars.items()) + "\n"
    env_path.write_text(env_content)
    console.print(f"\n[bold cyan]Environment written to:[/] {env_path}")

    # Write .gitignore if not present
    gitignore_path = workdir / ".gitignore"
    if not gitignore_path.exists():
        gitignore_path.write_text(
            ".env\n.venv/\n__pycache__/\n*.pyc\n.pytest_cache/\n"
            ".ruff_cache/\n.mypy_cache/\nworkflows/\n*.log\n"
            "node_modules/\n.next/\ntemporary_screenshots/\n"
        )
        console.print("[bold cyan]Created:[/] .gitignore")

    # Validate keys
    console.print("\n[bold cyan]Validating configuration...[/]")
    _check_key("ANTHROPIC_API_KEY", env_vars.get("ANTHROPIC_API_KEY"))
    _check_key("OPENAI_API_KEY", env_vars.get("OPENAI_API_KEY"))

    # Check tools
    console.print("\n[bold cyan]Checking tools...[/]")
    _check_tool("node", ["node", "--version"])
    _check_tool("npm", ["npm", "--version"])
    _check_tool("git", ["git", "--version"])
    _check_tool("python", ["python", "--version"])
    _check_tool("semgrep", ["semgrep", "--version"])

    # Sandbox setup
    console.print(f"\n[bold cyan]Sandbox mode:[/] {sandbox}")
    if sandbox == "gvisor":
        _check_tool("runsc (gVisor)", ["runsc", "--version"])

    # MCP integrations
    if mcp_list:
        mcps = [m.strip() for m in mcp_list.split(",")]
        console.print(f"\n[bold cyan]MCP integrations:[/] {', '.join(mcps)}")
        mcp_config = _configure_mcps(workdir, mcps)
        mcp_config_path = workdir / ".claude" / "mcp_config.json"
        mcp_config_path.write_text(json.dumps(mcp_config, indent=2))
        console.print(f"  Config written to: {mcp_config_path}")

    # Write mythos config
    config = {
        "version": "0.1.0",
        "workspace": str(workdir),
        "sandbox": sandbox,
        "mcp_integrations": [m.strip() for m in mcp_list.split(",")] if mcp_list else [],
        "keys_configured": {
            "anthropic": bool(env_vars.get("ANTHROPIC_API_KEY")),
            "openai": bool(env_vars.get("OPENAI_API_KEY")),
        },
    }
    config_path = workdir / ".claude" / "mythos.json"
    config_path.write_text(json.dumps(config, indent=2))

    # Summary
    console.print("\n")
    table = Table(title="Mythos Init Summary")
    table.add_column("Item", style="cyan")
    table.add_column("Status", style="green")
    table.add_row("Workspace", str(workdir))
    table.add_row("Directories", f"{len(DEFAULT_DIRS)} created")
    table.add_row("Anthropic Key", "set" if env_vars.get("ANTHROPIC_API_KEY") else "[red]missing[/]")
    table.add_row("OpenAI Key", "set" if env_vars.get("OPENAI_API_KEY") else "[yellow]optional[/]")
    table.add_row("Sandbox", sandbox)
    table.add_row("MCPs", mcp_list or "none")
    console.print(table)
    console.print("\n[bold green]Init complete.[/] Run [bold]mythos new <project-name>[/] to create a project.")


def _check_key(name: str, value: str | None):
    if value and len(value) > 10:
        console.print(f"  [green]PASS[/] {name} ({value[:8]}...)")
    else:
        console.print(f"  [yellow]SKIP[/] {name} (not set)")


def _check_tool(name: str, cmd: list[str]):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        version = r.stdout.strip().split("\n")[0] if r.stdout else "ok"
        console.print(f"  [green]PASS[/] {name}: {version}")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        console.print(f"  [red]FAIL[/] {name}: not found")


def _configure_mcps(workdir: Path, mcps: list[str]) -> dict:
    """Generate MCP configuration stubs."""
    config = {"integrations": {}}
    for mcp in mcps:
        if mcp == "firecrawl":
            config["integrations"]["firecrawl"] = {
                "type": "scraper",
                "endpoint": os.getenv("FIRECRAWL_URL", "https://api.firecrawl.dev"),
                "api_key_env": "FIRECRAWL_API_KEY",
                "capabilities": ["scrape", "map", "crawl", "extract"],
            }
        elif mcp == "nano-banana-2":
            config["integrations"]["nano-banana-2"] = {
                "type": "image_generation",
                "endpoint": os.getenv("NANO_BANANA_URL", "https://api.key.ai/v1"),
                "api_key_env": "NANO_BANANA_API_KEY",
                "capabilities": ["generate_4k", "cinematic", "conceptual_art"],
                "cost_per_image": 0.06,
            }
        elif mcp == "relume":
            config["integrations"]["relume"] = {
                "type": "wireframe",
                "capabilities": ["sitemap", "wireframe", "conversion_optimization"],
            }
        elif mcp == "stitch":
            config["integrations"]["stitch"] = {
                "type": "visual_ai",
                "capabilities": ["prototype", "extract_html_css", "ui_elements"],
            }
        elif mcp == "spline":
            config["integrations"]["spline"] = {
                "type": "3d_graphics",
                "capabilities": ["interactive_3d", "webgl", "scroll_animations"],
            }
        else:
            config["integrations"][mcp] = {"type": "custom", "capabilities": []}
            console.print(f"  [yellow]WARN[/] Unknown MCP '{mcp}' — added as custom stub")
    return config
