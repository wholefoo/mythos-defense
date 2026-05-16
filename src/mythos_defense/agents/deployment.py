"""Deployment Agent — produces hardened deploy config."""
from __future__ import annotations
import json
from mythos_defense.agents.base import BaseAgent, AgentResult


class DeploymentAgent(BaseAgent):
    name = "deployment"
    model = "claude-sonnet-4-6"
    max_tokens = 6000

    def run(self, brief: str, threat_model: dict) -> AgentResult:
        system = self._load_prompt("deployment")
        user = f"""# Project Brief

{brief}

# Threat Model

```json
{json.dumps(threat_model, indent=2)[:30000]}
```

Produce the deployment hardening JSON.
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
            raise ValueError(f"Deployment output not valid JSON: {e}")
        return result
