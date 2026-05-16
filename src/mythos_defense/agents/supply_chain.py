"""Supply Chain Agent."""
from __future__ import annotations
import json
import subprocess
from pathlib import Path
from mythos_defense.agents.base import BaseAgent, AgentResult


class SupplyChainAgent(BaseAgent):
    name = "supply_chain"
    model = "claude-sonnet-4-6"
    max_tokens = 8000

    def run(self, workspace: Path) -> AgentResult:
        system = self._load_prompt("supply_chain")

        audit_output = ""
        manifests = []

        if (workspace / "package.json").exists():
            manifests.append(("package.json", (workspace / "package.json").read_text()))
            try:
                r = subprocess.run(
                    ["npm", "audit", "--json"],
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                audit_output = r.stdout[:50000]
            except Exception as e:
                audit_output = f"(npm audit failed: {e})"

        elif (workspace / "requirements.txt").exists() or (workspace / "pyproject.toml").exists():
            manifest_name = "requirements.txt" if (workspace / "requirements.txt").exists() else "pyproject.toml"
            manifests.append((manifest_name, (workspace / manifest_name).read_text()))
            try:
                r = subprocess.run(
                    ["pip-audit", "--format", "json"],
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                audit_output = r.stdout[:50000]
            except Exception as e:
                audit_output = f"(pip-audit failed or not installed: {e})"

        manifest_block = "\n\n".join(f"### {name}\n```\n{c}\n```" for name, c in manifests)

        user = f"""# Audit Tool Output

```json
{audit_output or "(no audit output)"}
```

# Manifest Files

{manifest_block or "(no manifests found)"}

Produce the supply chain assessment JSON.
"""
        result = self._call(system, user)
        try:
            text = result.output.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result.structured = json.loads(text.strip())
        except json.JSONDecodeError as e:
            raise ValueError(f"Supply Chain output not valid JSON: {e}")
        return result
