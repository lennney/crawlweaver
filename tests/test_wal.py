"""Tests for WAL auto-save (Factor #6)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import MagicMock
from state import make_state, CrawlState
from knowledge import Knowledge


def test_crawl_accepts_state_path():
    """crawl() should accept state_path parameter."""
    from reducer import crawl
    import inspect
    sig = inspect.signature(crawl)
    assert "state_path" in sig.parameters


def test_checkpoint_saves_after_each_step(tmp_path):
    """State file should be written after each pipeline step."""
    state_path = tmp_path / "state.json"

    # Create a minimal state that will fail at extract (no real URL)
    state = make_state("https://invalid.test/nope", keyword="test")
    knowledge = Knowledge()
    llm = MagicMock()

    from reducer import crawl
    # This will fail at extract, but state_path should still be written
    result = crawl(state, knowledge, llm, state_path=str(state_path))

    # State should have been saved at least once
    assert state_path.exists(), "WAL: state should be saved even on failure"
    loaded = CrawlState.load(str(state_path))
    assert loaded.url == "https://invalid.test/nope"
