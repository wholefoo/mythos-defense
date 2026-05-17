"""Architect Agent — produces threat model from a brief."""
from __future__ import annotations
from mythos_defense.agents.base import BaseAgent, AgentResult
from mythos_defense.utils import parse_llm_json


class ArchitectAgent(BaseAgent):
    name = "architect"
    model = "claude-opus-4-7"
    max_tokens = 16000

    def run(self, brief: str) -> AgentResult:
        system = self._load_prompt("architect")
        user = f"# Project Brief\n\n{brief}\n\nProduce the threat model JSON."
        result = self._call(system, user)

        try:
            result.structured = parse_llm_json(result.output)
        except (ValueError, KeyError) as e:
            raise ValueError(f"Architect output not valid JSON: {e}\nRaw: {result.output[:500]}")

        return result
