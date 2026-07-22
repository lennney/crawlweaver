"""Tests for context module — constants and context building."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from context import (
    MAX_ARTICLE_CHARS,
    MAX_ARTICLE_PREVIEW_CHARS,
    MAX_SOURCE_CHARS,
    build_rewrite_context,
    build_seo_context,
    build_verify_context,
)
from knowledge import Knowledge
from state import make_state


def test_constants_exist():
    """Factor #3: context constants should be defined, not magic numbers."""
    assert isinstance(MAX_SOURCE_CHARS, int)
    assert isinstance(MAX_ARTICLE_CHARS, int)
    assert isinstance(MAX_ARTICLE_PREVIEW_CHARS, int)
    assert MAX_SOURCE_CHARS > 0
    assert MAX_ARTICLE_CHARS > 0
    assert MAX_ARTICLE_PREVIEW_CHARS > 0


def test_rewrite_context_truncates():
    """Source content should be truncated to MAX_SOURCE_CHARS."""
    state = make_state("https://example.com", keyword="test")
    state.raw_text = "x" * 10000
    ctx = build_rewrite_context(state, Knowledge())
    assert "x" * (MAX_SOURCE_CHARS + 1) not in ctx


def test_seo_context_truncates():
    """SEO context should truncate article to MAX_ARTICLE_PREVIEW_CHARS."""
    state = make_state("https://example.com", keyword="test")
    state.article_md = "y" * 5000
    ctx = build_seo_context(state)
    assert "y" * (MAX_ARTICLE_PREVIEW_CHARS + 1) not in ctx


def test_verify_context_truncates():
    """Verify context should truncate article to MAX_ARTICLE_CHARS."""
    state = make_state("https://example.com", keyword="test")
    state.raw_text = "x" * 10000
    state.article_md = "y" * 10000
    ctx = build_verify_context(state)
    assert "y" * (MAX_ARTICLE_CHARS + 1) not in ctx
