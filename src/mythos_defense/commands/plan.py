"""mythos plan — Claude plan mode: scope, wireframe, quality bar, clarifying questions."""
from __future__ import annotations
import json
import os
from pathlib import Path
import click
from rich.console import Console
from anthropic import Anthropic
from mythos_defense.utils import parse_llm_json

console = Console()

QUALITY_LEVELS = {
    1: "Basic prompting (avoid)",
    2: "Design education (UIUX Pro Max + Front-End Design skills)",
    3: "Visual director (Awwwards/Godly/Dribbble reference targets)",
    4: "The Cloner (extract raw HTML/CSS from premium reference sites)",
    5: "Custom components (21st.dev, CodePen, glassmorphism, interactive elements)",
    6: "Visual AI editors (Stitch 2.0 ideations)",
    7: "The Frontier (3D, WebGL, custom shaders, scroll-driven animations)",
}

PLAN_SYSTEM_PROMPT = """You are a senior web architect and UX strategist. Given a project brief, produce a comprehensive build plan.

You MUST output a single JSON object — no surrounding prose, no markdown fences:

{
  "project_name": "...",
  "target_audience": "...",
  "business_goals": ["..."],
  "aesthetic_direction": "...",
  "quality_level": 1-7,
  "clarifying_questions": ["Questions you need answered before proceeding (if any)"],
  "sitemap": [
    {"path": "/", "name": "Home", "purpose": "...", "sections": ["Hero", "Social Proof", "Features", "CTA"]},
    {"path": "/about", "name": "About", "purpose": "...", "sections": ["..."]}
  ],
  "wireframe_notes": {
    "layout_system": "grid|flex|hybrid",
    "responsive_breakpoints": ["mobile", "tablet", "desktop"],
    "navigation_pattern": "top-nav|sidebar|hamburger",
    "hero_style": "full-bleed|split|video-bg|3d-scene",
    "color_strategy": "monochrome|complementary|analogous|triadic",
    "typography_scale": "modular|custom",
    "animation_approach": "subtle|scroll-driven|cinematic|interactive-3d"
  },
  "component_inventory": [
    {"name": "...", "source": "shadcn|custom|21st.dev|codepen", "complexity": "low|medium|high"}
  ],
  "data_model": [
    {"entity": "...", "fields": ["..."], "relationships": ["..."]}
  ],
  "api_routes": [
    {"method": "GET|POST|PUT|DELETE", "path": "/api/...", "purpose": "...", "auth_required": true}
  ],
  "security_considerations": ["..."],
  "deployment_strategy": "...",
  "estimated_pages": 0,
  "estimated_components": 0,
  "estimated_api_routes": 0,
  "inspiration_sites": ["..."],
  "risks": ["..."]
}

Rules:
- The sitemap MUST follow a conversion-optimized user journey (Hero > Social Proof > Features > FAQ > CTA).
- Every component must have a named source (shadcn, custom, external library).
- Security considerations must map to OWASP Top 10.
- If the brief is ambiguous, add clarifying_questions rather than guessing.
- Quality level must match or exceed the requested bar.
"""


@click.command("plan")
@click.option("--brief", "-b", required=True, type=click.Path(exists=True, path_type=Path),
              help="Path to project brief markdown.")
@click.option("--inspiration", "-i", default=None,
              help="Comma-separated inspiration sources: awwwards,godly,dribbble.")
@click.option("--quality-bar", "-q", default=5, type=click.IntRange(1, 7),
              help="Minimum quality level (1-7, see docs).")
@click.option("--emit", "-e", default="plan.json", type=click.Path(path_type=Path),
              help="Output path for the plan file.")
@click.option("--model", default="claude-opus-4-7",
              help="Model to use for planning.")
def plan_cmd(brief: Path, inspiration: str | None, quality_bar: int, emit: Path, model: str):
    """Generate a comprehensive build plan from a project brief."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[red]ANTHROPIC_API_KEY not set.[/]")
        raise SystemExit(1)

    brief_text = brief.read_text()
    console.rule("[bold]Mythos Plan")
    console.print(f"Brief: {brief}")
    console.print(f"Quality bar: Level {quality_bar} — {QUALITY_LEVELS.get(quality_bar, 'Unknown')}")
    if inspiration:
        console.print(f"Inspiration: {inspiration}")

    # Build user prompt
    user_prompt = f"""# Project Brief

{brief_text}

# Requirements

- Minimum quality level: {quality_bar} ({QUALITY_LEVELS.get(quality_bar, '')})
- Inspiration sources: {inspiration or 'none specified — use your judgment'}
- Enforce conversion-optimized structure (Hero > Social Proof > Features > FAQ > CTA)
- Include security considerations for all user-facing features

Produce the plan JSON.
"""

    console.print("\n[bold cyan]Generating plan with Claude...[/]")
    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=16000,
        system=PLAN_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    output = response.content[0].text.strip()

    # Parse JSON
    try:
        plan = parse_llm_json(output)
    except (json.JSONDecodeError, ValueError) as e:
        console.print(f"[red]Failed to parse plan JSON:[/] {e}")
        console.print(f"Raw output saved to plan_raw.txt")
        Path("plan_raw.txt").write_text(output)
        raise SystemExit(1)

    # Enforce quality bar
    plan_quality = plan.get("quality_level", 1)
    if plan_quality < quality_bar:
        console.print(f"[yellow]Plan quality ({plan_quality}) below bar ({quality_bar}). Adjusting...[/]")
        plan["quality_level"] = quality_bar

    # Write plan
    emit.parent.mkdir(parents=True, exist_ok=True)
    emit.write_text(json.dumps(plan, indent=2))

    # Display summary
    console.print(f"\n[bold green]Plan generated:[/] {emit}")
    console.print(f"  Pages: {plan.get('estimated_pages', '?')}")
    console.print(f"  Components: {plan.get('estimated_components', '?')}")
    console.print(f"  API routes: {plan.get('estimated_api_routes', '?')}")
    console.print(f"  Quality level: {plan.get('quality_level', '?')}")

    if plan.get("clarifying_questions"):
        console.print("\n[bold yellow]Clarifying questions:[/]")
        for q in plan["clarifying_questions"]:
            console.print(f"  ? {q}")
        console.print("\nAnswer these in your brief and re-run [bold]mythos plan[/].")

    console.print(f"\n  Tokens: {response.usage.input_tokens} in / {response.usage.output_tokens} out")
    console.print("\nNext: [bold]mythos build --plan plan.json[/]")
