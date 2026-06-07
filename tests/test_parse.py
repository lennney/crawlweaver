"""Tests for shared JSON parse utility."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from tools.parse import parse_json, parse_llm_output


class TestParseJson:
    def test_valid_json(self):
        assert parse_json('{"a": 1}') == {"a": 1}

    def test_json_in_code_block(self):
        text = '```json\n{"a": 1}\n```'
        assert parse_json(text) == {"a": 1}

    def test_json_with_surrounding_text(self):
        text = 'Here is the result: {"a": 1} done.'
        assert parse_json(text) == {"a": 1}

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            parse_json("no json here")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            parse_json("")


class TestParseLlmOutput:
    def test_normal_markdown(self):
        result = parse_llm_output("# Title\n\nSome content.", min_length=5)
        assert result == "# Title\n\nSome content."

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            parse_llm_output("")

    def test_too_short_raises(self):
        with pytest.raises(ValueError, match="too short"):
            parse_llm_output("hi", min_length=100)

    def test_strips_think_tags(self):
        result = parse_llm_output(
            "<think>reasoning step 1, reasoning step 2, reasoning step 3</think>\n\n"
            "# Article Title\nContent here with enough text to pass minimum length check.",
            min_length=10,
        )
        assert "<think>" not in result
        assert "# Article" in result
