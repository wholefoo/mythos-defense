"""mythos review — visual QA via Playwright screenshots + AI review."""
from __future__ import annotations
import json
import os
import subprocess
import time
from pathlib import Path
import click
from rich.console import Console
from anthropic import Anthropic
import base64

console = Console()

REVIEW_SYSTEM_PROMPT = """You are a senior UI/UX reviewer. You are shown a screenshot of a web page. Identify issues with:

1. Layout — alignment, spacing, overflow, responsive breakpoints
2. Typography — hierarchy, readability, font consistency
3. Color — contrast ratios (WCAG AA minimum), palette cohesion
4. Components — broken/missing elements, hover states, interactive feedback
5. Content — placeholder text remaining, broken images, lorem ipsum
6. Consistency — design system violations, inconsistent padding/margins

Output a single JSON object:

{
  "page": "url or page name",
  "score": 1-10,
  "issues": [
    {
      "severity": "critical|major|minor|cosmetic",
      "category": "layout|typography|color|components|content|consistency",
      "description": "What's wrong",
      "location": "Where on the page (top-left, hero section, footer, etc.)",
      "fix": "Specific CSS/component fix recommendation"
    }
  ],
  "passed": true/false,
  "summary": "One-line overall assessment"
}

Rules:
- Score 8+ means ship-ready
- critical/major issues mean passed=false
- Be specific about fixes (give actual Tailwind classes or CSS properties)
- Check mobile AND desktop if both screenshots provided
"""


@click.command("review")
@click.option("--workspace", "-w", default=".", type=click.Path(exists=True, path_type=Path),
              help="Project workspace.")
@click.option("--passes", "-p", default=2, type=int,
              help="Minimum review passes before approval.")
@click.option("--screenshots", "-s", default="./temporary_screenshots",
              type=click.Path(path_type=Path), help="Screenshot output directory.")
@click.option("--fix", "fix_categories", default="layout,padding,typography,contrast",
              help="Comma-separated categories to auto-fix.")
@click.option("--url", default="http://localhost:3000",
              help="URL of the running dev server.")
@click.option("--port", default=3000, type=int,
              help="Dev server port (will start if not running).")
@click.option("--model", default="claude-sonnet-4-6")
def review_cmd(workspace: Path, passes: int, screenshots: Path, fix_categories: str,
               url: str, port: int, model: str):
    """Run visual QA: screenshot pages, AI review, auto-fix, repeat."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[red]ANTHROPIC_API_KEY not set.[/]")
        raise SystemExit(1)

    workspace = workspace.resolve()
    screenshots = screenshots.resolve()
    screenshots.mkdir(parents=True, exist_ok=True)

    console.rule("[bold]Mythos Review")
    console.print(f"Workspace: {workspace}")
    console.print(f"URL: {url}")
    console.print(f"Passes: {passes}")
    console.print(f"Fix categories: {fix_categories}")

    # Check Playwright is available
    if not _check_playwright():
        console.print("[red]Playwright not installed. Install with:[/]")
        console.print("  npm install -D playwright @playwright/test")
        console.print("  npx playwright install chromium")
        raise SystemExit(1)

    # Start dev server if not running
    server_proc = None
    if not _is_server_running(url):
        console.print(f"\n[bold cyan]Starting dev server on port {port}...[/]")
        server_proc = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=workspace,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(5)

    client = Anthropic(api_key=api_key)
    all_passed = False

    for pass_num in range(1, passes + 1):
        console.print(f"\n[bold cyan]--- Review Pass {pass_num}/{passes} ---[/]")

        # Take screenshots
        screenshot_files = _take_screenshots(workspace, url, screenshots, pass_num)
        if not screenshot_files:
            console.print("[red]No screenshots captured.[/]")
            break

        # Review each screenshot
        pass_issues = []
        for ss_file in screenshot_files:
            console.print(f"  Reviewing: {ss_file.name}")
            review = _review_screenshot(client, model, ss_file)
            if review:
                pass_issues.extend(review.get("issues", []))
                score = review.get("score", 0)
                status = "[green]PASS" if review.get("passed") else "[red]FAIL"
                console.print(f"    {status}[/] Score: {score}/10 — {review.get('summary', '')}")

                for issue in review.get("issues", []):
                    sev = issue.get("severity", "?")
                    console.print(f"      [{_sev_color(sev)}]{sev}[/] {issue['description']}")

        # Auto-fix if issues found
        fixable = [i for i in pass_issues
                   if i.get("category") in fix_categories.split(",")
                   and i.get("severity") in ("critical", "major")]

        if fixable and pass_num < passes:
            console.print(f"\n  [cyan]Auto-fixing {len(fixable)} issues...[/]")
            _auto_fix(client, model, workspace, fixable)

        if not any(i.get("severity") in ("critical", "major") for i in pass_issues):
            all_passed = True
            console.print(f"\n[bold green]All pages passed review on pass {pass_num}.[/]")
            break

    # Cleanup
    if server_proc:
        server_proc.terminate()

    # Write review report
    report_path = screenshots / "review_report.json"
    report_path.write_text(json.dumps({
        "passes_completed": pass_num,
        "all_passed": all_passed,
        "final_issues": pass_issues,
    }, indent=2))

    if all_passed:
        console.print("\nNext: [bold]mythos harden[/]")
    else:
        console.print(f"\n[yellow]Review incomplete. {len(pass_issues)} issues remain.[/]")
        console.print("Fix manually and re-run [bold]mythos review[/].")


def _check_playwright() -> bool:
    try:
        r = subprocess.run(["npx", "playwright", "--version"],
                           capture_output=True, text=True, timeout=15)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _is_server_running(url: str) -> bool:
    try:
        import httpx
        r = httpx.get(url, timeout=3)
        return r.status_code < 500
    except Exception:
        return False


def _take_screenshots(workspace: Path, url: str, output_dir: Path, pass_num: int) -> list[Path]:
    """Use Playwright to capture screenshots of all pages."""
    script = f"""
const {{ chromium }} = require('playwright');
(async () => {{
    const browser = await chromium.launch();
    const page = await browser.newPage();
    const pages = ['/', '/about', '/contact', '/pricing'];
    for (const p of pages) {{
        try {{
            await page.goto('{url}' + p, {{ waitUntil: 'networkidle', timeout: 10000 }});
            await page.screenshot({{ path: '{output_dir.as_posix()}/pass{pass_num}_' + p.replace('/', 'home').replace('/', '_') + '.png', fullPage: true }});
        }} catch(e) {{
            // page might not exist
        }}
    }}
    await browser.close();
}})();
"""
    script_path = workspace / "_mythos_screenshot.js"
    script_path.write_text(script)
    try:
        subprocess.run(["node", str(script_path)], cwd=workspace,
                       capture_output=True, text=True, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    finally:
        script_path.unlink(missing_ok=True)

    return sorted(output_dir.glob(f"pass{pass_num}_*.png"))


def _review_screenshot(client: Anthropic, model: str, screenshot_path: Path) -> dict | None:
    """Send screenshot to Claude for visual review."""
    try:
        image_data = base64.b64encode(screenshot_path.read_bytes()).decode()
    except Exception:
        return None

    response = client.messages.create(
        model=model,
        max_tokens=4000,
        system=REVIEW_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_data}},
                {"type": "text", "text": f"Review this page screenshot: {screenshot_path.name}. Output JSON only."},
            ],
        }],
    )

    output = response.content[0].text.strip()
    try:
        if output.startswith("```"):
            output = output.split("```")[1]
            if output.startswith("json"):
                output = output[4:]
        return json.loads(output.strip())
    except json.JSONDecodeError:
        return None


def _auto_fix(client: Anthropic, model: str, workspace: Path, issues: list[dict]):
    """Attempt to auto-fix issues by generating patches."""
    fixes_prompt = json.dumps(issues, indent=2)
    response = client.messages.create(
        model=model,
        max_tokens=8000,
        system="You are a frontend developer. Given UI issues, generate fixes as file edits. Output JSON: {\"files\": [{\"path\": \"...\", \"content\": \"full updated file\"}]}",
        messages=[{"role": "user", "content": f"Fix these UI issues:\n{fixes_prompt}\n\nOutput JSON only."}],
    )
    output = response.content[0].text.strip()
    try:
        if output.startswith("```"):
            output = output.split("```")[1]
            if output.startswith("json"):
                output = output[4:]
        result = json.loads(output.strip())
        for f in result.get("files", []):
            file_path = workspace / f["path"]
            if file_path.exists():
                file_path.write_text(f["content"])
                console.print(f"    [green]fixed[/] {f['path']}")
    except (json.JSONDecodeError, KeyError):
        pass


def _sev_color(severity: str) -> str:
    return {"critical": "red", "major": "yellow", "minor": "dim", "cosmetic": "dim"}.get(severity, "white")
