"""Blue Team Agent — patches findings."""
from __future__ import annotations
import logging
from pathlib import Path
from mythos_defense.agents.base import BaseAgent, AgentResult
from mythos_defense.schemas.findings import Finding
from mythos_defense.utils import parse_llm_json

logger = logging.getLogger(__name__)


class BlueTeamAgent(BaseAgent):
    name = "blue_team"
    model = "claude-sonnet-4-6"
    max_tokens = 16000

    def run(
        self,
        finding: Finding,
        workspace: Path,
        prior_attempts: list[dict] | None = None,
    ) -> AgentResult:
        system = self._load_prompt("blue_team")

        file_contents = []
        resolved_ws = workspace.resolve()
        for loc in finding.affected_locations:
            file_path = workspace / loc.path
            # Security: prevent path traversal outside workspace
            if not file_path.resolve().is_relative_to(resolved_ws):
                logger.warning("Path traversal blocked: %s", loc.path)
                continue
            if file_path.exists() and file_path.is_file():
                content = file_path.read_text()
                file_contents.append(f"### {loc.path}\n```\n{content}\n```")

        prior_text = ""
        if prior_attempts:
            prior_text = "\n\n## Prior Failed Attempts\n\n" + "\n\n".join(
                f"Attempt {i+1}: {a.get('rationale', '')}\nWhy it failed: {a.get('failure', '')}"
                for i, a in enumerate(prior_attempts)
            )

        user = f"""# Finding

```json
{finding.model_dump_json(indent=2)}
```

# Affected Files

{chr(10).join(file_contents) if file_contents else "(no files readable from affected_locations)"}
{prior_text}

Produce the patch JSON.
"""
        result = self._call(system, user)

        try:
            result.structured = parse_llm_json(result.output)
        except (ValueError, KeyError) as e:
            raise ValueError(f"Blue Team output not valid JSON: {e}\nRaw: {result.output[:500]}")

        return result
