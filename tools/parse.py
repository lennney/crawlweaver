"""Shared parsing utilities for LLM output.

Factor #4: Tools are structured outputs.
Centralizes JSON extraction and output validation.
"""

import json
import re


def parse_json(text: str) -> dict:
    """Extract JSON from LLM response. Tries 3 strategies.

    1. Direct json.loads
    2. Extract from ```json...``` code block
    3. Find first { to last }

    Raises ValueError if no valid JSON found.
    """
    if not text or not text.strip():
        raise ValueError("Cannot parse JSON from empty string")

    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: code block
    m = re.search(r"```(?:json)?\s*\n?(.+?)\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: first { to last }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Cannot parse JSON from LLM response: {text[:200]}")


def parse_llm_output(text: str, min_length: int = 50) -> str:
    """Validate and clean LLM text output.

    Handles multiple thinking/reasoning formats:
    - <think>...</think> (XML-style, e.g. minimax-m3)
    - Thinking. 1. ... (plain-text numbered, OpenCode Go)
    - All other known prefixes from reasoning models

    - Checks minimum length
    - Raises ValueError on empty/invalid output
    """
    if not text or not text.strip():
        raise ValueError("LLM returned empty output")

    cleaned = text

    # 1. Strip <think>...</think> blocks (common in minimax-m3, GLM, etc.)
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()

    # 2. Strip "Thinking. N. ..." blocks that appear before actual output.
    #    These start at the beginning and end when actual content markers appear.
    #    Markers: markdown headings, code blocks, JSON, or triple dashes.
    thinking_pattern = (
        r"^Thinking\.\s+\d+\.\s+"
        r".*?"
        r"(?=(?:\n\n|\n)(?:#{1,3}\s|```|(?:\*\*[\w\s]+\*\*:?)|-{3,}|\n\n))"
    )
    cleaned = re.sub(thinking_pattern, "", cleaned, count=1, flags=re.DOTALL | re.MULTILINE).strip()

    if len(cleaned) < min_length:
        raise ValueError(f"LLM output too short ({len(cleaned)} < {min_length}): {cleaned[:100]}")

    return cleaned
