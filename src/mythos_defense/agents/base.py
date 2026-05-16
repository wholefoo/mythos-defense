"""Base class for defensive agents."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import os
from anthropic import Anthropic


@dataclass
class AgentResult:
    output: str
    structured: dict[str, Any]
    tokens_in: int
    tokens_out: int
    model: str


class BaseAgent:
    name: str = "abstract"
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 8000

    def __init__(self, api_key: str | None = None):
        self.client = Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])

    def _load_prompt(self, name: str) -> str:
        path = Path(__file__).parent.parent / "prompts" / f"{name}.md"
        return path.read_text()

    def _call(self, system: str, user: str) -> AgentResult:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = response.content[0].text
        return AgentResult(
            output=text,
            structured={},
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            model=self.model,
        )
