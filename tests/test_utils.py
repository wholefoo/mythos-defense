"""Tests for shared utilities."""
import pytest
from mythos_defense.utils import parse_llm_json, sev_color


class TestParseLlmJson:
    def test_plain_json(self):
        result = parse_llm_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_fenced_json(self):
        raw = '```json\n{"key": "value"}\n```'
        result = parse_llm_json(raw)
        assert result == {"key": "value"}

    def test_fenced_no_language(self):
        raw = '```\n{"key": 123}\n```'
        result = parse_llm_json(raw)
        assert result == {"key": 123}

    def test_whitespace(self):
        raw = '  \n  {"a": 1}  \n  '
        result = parse_llm_json(raw)
        assert result == {"a": 1}

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            parse_llm_json("not json at all")

    def test_nested_fences(self):
        # Nested fences are a known edge case — the split approach can't handle them.
        # Verify we get a JSONDecodeError rather than a silent wrong result.
        raw = '```json\n{"code": "```example```"}\n```'
        import pytest
        with pytest.raises(Exception):
            parse_llm_json(raw)


class TestSevColor:
    def test_critical(self):
        assert sev_color("critical") == "red"
        assert sev_color("CRITICAL") == "red"

    def test_unknown(self):
        assert sev_color("unknown") == "white"

    def test_low(self):
        assert sev_color("LOW") == "dim"
