"""Architect Agent — produces threat model from a brief."""
from __future__ import annotations
import json
from mythos_defense.agents.base import BaseAgent, AgentResult


class ArchitectAgent(BaseAgent):
    name = "architect"
    model = "claude-opus-4-7"
    max_tokens = 16000

    def run(self, brief: str) -> AgentResult:
        system = self._load_prompt("architect")
        user = f"# Project Brief\n\n{brief}\n\nProduce the threat model JSON."
        result = self._call(system, user)

        try:
            text = result.output.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result.structured = json.loads(text.strip())
        except json.JSONDecodeError as e:
            raise ValueError(f"Architect output not valid JSON: {e}\nRaw: {result.output[:500]}")

        return result
