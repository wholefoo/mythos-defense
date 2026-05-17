"""mythos new — scaffold a new project with the specified stack."""
from __future__ import annotations
import json
import subprocess
from pathlib import Path
import click
from rich.console import Console

console = Console()

STACK_CONFIGS = {
    "next": {
        "cmd": ["npx", "create-next-app@latest", "{name}", "--typescript",
                "--tailwind", "--eslint", "--app", "--src-dir",
                "--import-alias", "@/*", "--use-npm"],
        "description": "Next.js with TypeScript and App Router",
    },
    "tailwind": {
        "post_install": [],
        "description": "Tailwind CSS (included via create-next-app --tailwind)",
    },
    "shadcn": {
        "cmd": ["npx", "shadcn@latest", "init", "--defaults", "--force"],
        "post_install": ["npx", "shadcn@latest", "add", "button", "card", "input",
                         "label", "dialog", "dropdown-menu", "toast"],
        "description": "Shadcn UI component library",
    },
    "supabase": {
        "deps": ["@supabase/supabase-js", "@supabase/ssr"],
        "env_vars": {"NEXT_PUBLIC_SUPABASE_URL": "", "NEXT_PUBLIC_SUPABASE_ANON_KEY": ""},
        "description": "Supabase (PostgreSQL + Auth + Realtime)",
    },
    "stripe": {
        "deps": ["stripe", "@stripe/stripe-js"],
        "env_vars": {"STRIPE_SECRET_KEY": "", "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY": ""},
        "description": "Stripe (checkout + payments)",
    },
    "resend": {
        "deps": ["resend"],
        "env_vars": {"RESEND_API_KEY": ""},
        "description": "Resend (transactional email)",
    },
}

HOSTING_CONFIGS = {
    "vercel": {"deploy_cmd": "npx vercel", "config_file": "vercel.json"},
    "netlify": {"deploy_cmd": "npx netlify deploy --prod", "config_file": "netlify.toml"},
    "github-pages": {"deploy_cmd": "npm run build && npm run export", "config_file": None},
}


@click.command("new")
@click.argument("name")
@click.option("--stack", "-s", default="next,tailwind,shadcn",
              help="Comma-separated stack components.")
@click.option("--hosting", "-h", default="vercel",
              type=click.Choice(["vercel", "netlify", "github-pages"]),
              help="Target hosting platform.")
@click.option("--assets", default="local",
              help="Asset storage: 'local', 'cloudflare-r2', 's3'.")
@click.option("--workflows", "workflow_engines", default=None,
              help="Workflow engines: 'modal', 'trigger.dev'.")
@click.option("--dir", "parent_dir", default=".", type=click.Path(path_type=Path),
              help="Parent directory to create project in.")
def new_cmd(name: str, stack: str, hosting: str, assets: str,
            workflow_engines: str | None, parent_dir: Path):
    """Scaffold a new project with the specified tech stack."""
    parent_dir = parent_dir.resolve()
    project_dir = parent_dir / name

    if project_dir.exists():
        console.print(f"[red]Directory already exists:[/] {project_dir}")
        raise SystemExit(1)

    stack_items = [s.strip() for s in stack.split(",")]
    console.rule(f"[bold]Mythos New: {name}")
    console.print(f"Stack: {', '.join(stack_items)}")
    console.print(f"Hosting: {hosting}")
    console.print(f"Assets: {assets}")
    console.print(f"Directory: {project_dir}")

    # Step 1: Create Next.js app if 'next' in stack
    if "next" in stack_items:
        console.print("\n[bold cyan]Creating Next.js application...[/]")
        cmd = [c.replace("{name}", name) for c in STACK_CONFIGS["next"]["cmd"]]
        r = subprocess.run(cmd, cwd=parent_dir, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            console.print(f"[red]create-next-app failed:[/] {r.stderr[:500]}")
            raise SystemExit(1)
        console.print("[green]Next.js app created.[/]")
    else:
        project_dir.mkdir(parents=True)
        subprocess.run(["npm", "init", "-y"], cwd=project_dir, capture_output=True)

    # Step 2: Shadcn UI
    if "shadcn" in stack_items:
        console.print("\n[bold cyan]Initializing Shadcn UI...[/]")
        shadcn_cfg = STACK_CONFIGS["shadcn"]
        subprocess.run(shadcn_cfg["cmd"], cwd=project_dir, capture_output=True, text=True, timeout=120)
        if shadcn_cfg.get("post_install"):
            console.print("  Adding base components...")
            subprocess.run(shadcn_cfg["post_install"], cwd=project_dir,
                           capture_output=True, text=True, timeout=120)
        console.print("[green]Shadcn UI initialized.[/]")

    # Step 3: Install additional dependencies
    all_deps = []
    env_vars = {}
    for item in stack_items:
        cfg = STACK_CONFIGS.get(item, {})
        if "deps" in cfg:
            all_deps.extend(cfg["deps"])
        if "env_vars" in cfg:
            env_vars.update(cfg["env_vars"])

    if all_deps:
        console.print(f"\n[bold cyan]Installing dependencies:[/] {', '.join(all_deps)}")
        subprocess.run(["npm", "install"] + all_deps, cwd=project_dir,
                       capture_output=True, text=True, timeout=300)
        console.print("[green]Dependencies installed.[/]")

    # Step 4: Create Mythos project structure
    console.print("\n[bold cyan]Creating Mythos directories...[/]")
    for d in [".claude", "workflows", "tools", "brand_assets", "temporary_screenshots"]:
        (project_dir / d).mkdir(exist_ok=True)

    # Step 5: Write .env.local with placeholders
    env_local = project_dir / ".env.local"
    env_lines = [f"{k}={v}" for k, v in env_vars.items()]
    env_local.write_text("\n".join(env_lines) + "\n")
    console.print(f"  .env.local with {len(env_vars)} placeholders")

    # Step 6: Hosting config
    console.print(f"\n[bold cyan]Configuring hosting:[/] {hosting}")
    _write_hosting_config(project_dir, hosting)

    # Step 7: Write project manifest
    manifest = {
        "name": name,
        "stack": stack_items,
        "hosting": hosting,
        "assets": assets,
        "workflows": workflow_engines.split(",") if workflow_engines else [],
        "created_by": "mythos-defense",
        "version": "0.1.0",
    }
    (project_dir / ".claude" / "project.json").write_text(json.dumps(manifest, indent=2))

    # Step 8: Git init
    console.print("\n[bold cyan]Initializing git...[/]")
    subprocess.run(["git", "init"], cwd=project_dir, capture_output=True)
    _write_gitignore(project_dir)

    # Summary
    console.print(f"\n[bold green]Project '{name}' created at {project_dir}[/]")
    console.print("\nNext steps:")
    console.print(f"  cd {name}")
    console.print("  mythos plan --brief ./brief.md")


def _write_hosting_config(project_dir: Path, hosting: str):
    if hosting == "vercel":
        config = {"buildCommand": "npm run build", "outputDirectory": ".next"}
        (project_dir / "vercel.json").write_text(json.dumps(config, indent=2))
    elif hosting == "netlify":
        config = "[build]\n  command = \"npm run build\"\n  publish = \".next\"\n\n[[plugins]]\n  package = \"@netlify/plugin-nextjs\"\n"
        (project_dir / "netlify.toml").write_text(config)


def _write_gitignore(project_dir: Path):
    gitignore = project_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(
            "node_modules/\n.next/\n.env\n.env.local\n.env*.local\n"
            "temporary_screenshots/\nworkflows/\n*.log\n"
        )
