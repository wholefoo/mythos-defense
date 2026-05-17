"""mythos build — autonomous code generation from a plan."""
from __future__ import annotations
import json
import logging
import os
import time
from pathlib import Path
import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from anthropic import Anthropic
from mythos_defense.utils import parse_llm_json

logger = logging.getLogger(__name__)

console = Console()

BUILD_SYSTEM_PROMPT = """You are a senior full-stack developer building a premium website. You receive a structured plan and generate production-quality code.

For each page/component you generate, you MUST:
1. Use TypeScript with strict types
2. Follow the project's design system (Tailwind + Shadcn conventions)
3. Implement responsive design (mobile-first)
4. Add appropriate aria labels and semantic HTML
5. Use server components by default, client components only when interactivity is needed
6. Implement error boundaries and loading states
7. Follow security best practices (no dangerouslySetInnerHTML, sanitize inputs, parameterized queries)

Output format — a single JSON object:

{
  "files": [
    {"path": "src/app/page.tsx", "content": "full file content here"},
    {"path": "src/components/Hero.tsx", "content": "..."}
  ],
  "dependencies_to_add": ["package-name"],
  "env_vars_needed": {"KEY": "description"},
  "notes": "anything the developer should know"
}

Rules:
- Generate COMPLETE files, not snippets
- Use Next.js App Router conventions (layout.tsx, page.tsx, loading.tsx, error.tsx)
- Import from @/ alias
- Use Shadcn components where applicable (import from @/components/ui/...)
- NEVER hardcode API keys or secrets
- Include proper TypeScript interfaces/types
- Generate one batch of files per response (up to 15 files)
"""

AGENT_PROMPTS = {
    "architect": "Focus on the data model, API routes, middleware, and auth flow. Generate types, database schema, and API route handlers.",
    "implementation": "Focus on UI components, pages, layouts, and styling. Generate the visual layer with proper Tailwind classes and Shadcn components.",
}


@click.command("build")
@click.option("--plan", "-p", required=True, type=click.Path(exists=True, path_type=Path),
              help="Path to plan.json from 'mythos plan'.")
@click.option("--workspace", "-w", default=".", type=click.Path(exists=True, path_type=Path),
              help="Project workspace directory.")
@click.option("--agent", "-a", "agents", multiple=True, default=["architect", "implementation"],
              type=click.Choice(["architect", "implementation"]),
              help="Agents to run (can specify multiple).")
@click.option("--skills", default=None,
              help="Comma-separated skills to apply: frontend-design,uiux-pro-max,site-teardown,awesome-design.")
@click.option("--model", default="claude-sonnet-4-6",
              help="Model to use for code generation.")
@click.option("--max-tokens", default=16000, type=int)
@click.option("--dry-run", is_flag=True, help="Show what would be generated without writing files.")
def build_cmd(plan: Path, workspace: Path, agents: tuple, skills: str | None,
              model: str, max_tokens: int, dry_run: bool):
    """Autonomously generate code from a plan using AI agents."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[red]ANTHROPIC_API_KEY not set.[/]")
        raise SystemExit(1)

    workspace = workspace.resolve()
    plan_data = json.loads(plan.read_text())

    console.rule("[bold]Mythos Build")
    console.print(f"Plan: {plan}")
    console.print(f"Workspace: {workspace}")
    console.print(f"Agents: {', '.join(agents)}")
    console.print(f"Model: {model}")
    if skills:
        console.print(f"Skills: {skills}")
    if dry_run:
        console.print("[yellow]DRY RUN — no files will be written[/]")

    client = Anthropic(api_key=api_key)
    total_files = 0
    total_tokens_in = 0
    total_tokens_out = 0

    for agent_name in agents:
        console.print(f"\n[bold cyan]Running agent: {agent_name}[/]")
        agent_focus = AGENT_PROMPTS.get(agent_name, "")

        skill_context = ""
        if skills:
            skill_context = f"\n\nApply these design skills: {skills}. Ensure premium visual quality matching the quality bar in the plan."

        user_prompt = f"""# Build Plan

```json
{json.dumps(plan_data, indent=2)}
```

# Agent Focus

{agent_focus}
{skill_context}

# Existing Files in Workspace

{_list_existing_files(workspace)}

Generate the files for your area of responsibility. Output JSON only.
"""

        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      console=console) as progress:
            task = progress.add_task(f"  {agent_name} generating code...", total=None)

            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=BUILD_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )

            progress.update(task, completed=True)

        total_tokens_in += response.usage.input_tokens
        total_tokens_out += response.usage.output_tokens

        output = response.content[0].text.strip()
        try:
            result = parse_llm_json(output)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Failed to parse %s output: %s", agent_name, e)
            console.print(f"[red]  Failed to parse {agent_name} output:[/] {e}")
            raw_path = workspace / f"build_raw_{agent_name}.txt"
            raw_path.write_text(output)
            console.print(f"  Raw output saved to: {raw_path}")
            continue

        files = result.get("files", [])
        console.print(f"  Generated {len(files)} files")

        if not dry_run:
            for f in files:
                file_path = workspace / f["path"]
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(f["content"])
                console.print(f"    [green]wrote[/] {f['path']}")
                total_files += 1

            # Install new deps
            new_deps = result.get("dependencies_to_add", [])
            if new_deps:
                console.print(f"  [cyan]Installing:[/] {', '.join(new_deps)}")
                import subprocess
                subprocess.run(["npm", "install"] + new_deps, cwd=workspace,
                               capture_output=True, text=True, timeout=120)

            # Note env vars
            env_vars = result.get("env_vars_needed", {})
            if env_vars:
                console.print("  [yellow]Environment variables needed:[/]")
                for k, desc in env_vars.items():
                    console.print(f"    {k}: {desc}")
        else:
            for f in files:
                console.print(f"    [dim]would write[/] {f['path']}")
            total_files += len(files)

        if result.get("notes"):
            console.print(f"  [dim]Notes: {result['notes']}[/]")

    # Summary
    console.print(f"\n[bold green]Build complete.[/]")
    console.print(f"  Files {'generated' if dry_run else 'written'}: {total_files}")
    console.print(f"  Tokens: {total_tokens_in} in / {total_tokens_out} out")
    console.print("\nNext: [bold]mythos review[/]")


def _list_existing_files(workspace: Path, max_files: int = 50) -> str:
    """List key files in workspace for context."""
    patterns = ["**/*.tsx", "**/*.ts", "**/*.json"]
    files = []
    for pattern in patterns:
        for f in workspace.glob(pattern):
            rel = f.relative_to(workspace)
            if "node_modules" in str(rel) or ".next" in str(rel):
                continue
            files.append(str(rel))
            if len(files) >= max_files:
                break
    if not files:
        return "(empty project)"
    return "\n".join(f"- {f}" for f in sorted(files)[:max_files])
