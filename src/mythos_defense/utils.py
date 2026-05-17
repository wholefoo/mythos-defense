"""Shared utilities for Mythos Defense."""
from __future__ import annotations
import json
import logging

logger = logging.getLogger(__name__)


def parse_llm_json(raw: str) -> dict:
    """Parse JSON from LLM output, stripping markdown fences if present.

    Handles common patterns like:
        ```json\n{...}\n```
        ```\n{...}\n```
        raw JSON
    """
    text = raw.strip()
    if text.startswith("```"):
        # Extract content between first pair of fences
        parts = text.split("```")
        if len(parts) >= 3:
            text = parts[1]
        else:
            text = parts[1] if len(parts) > 1 else text
        # Strip optional language tag
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def sev_color(severity: str) -> str:
    """Map severity level to a Rich color name."""
    return {
        "CRITICAL": "red",
        "critical": "red",
        "HIGH": "red",
        "major": "yellow",
        "MEDIUM": "yellow",
        "minor": "dim",
        "LOW": "dim",
        "cosmetic": "dim",
        "INFO": "blue",
    }.get(severity, "white")
