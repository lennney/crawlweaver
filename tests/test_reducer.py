"""Basic tests for CrawlWeaver."""

import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from knowledge import Knowledge, load_knowledge, save_knowledge
from state import CrawlState, SeoMetadata, make_state


def test_make_state():
    state = make_state("https://youtube.com/watch?v=test123", keyword="hiking tips")
    assert state.url == "https://youtube.com/watch?v=test123"
    assert state.keyword == "hiking tips"
    assert state.step.value == "pending"
    assert len(state.events) == 0


def test_state_json_roundtrip():
    state = make_state("https://example.com", source="web", keyword="test")
    state.raw_text = "Hello world"
    state.article_md = "# Test Article"
    state.seo = SeoMetadata(title_tag="Test Title", meta_description="A test")

    json_str = state.to_json()
    restored = CrawlState.from_json(json_str)

    assert restored.url == state.url
    assert restored.raw_text == state.raw_text
    assert restored.seo.title_tag == "Test Title"


def test_state_events():
    state = make_state("https://example.com")
    state.append_event("extract", True, "Got 500 chars")
    state.append_event("rewrite", False, "LLM timeout", error="timeout")

    assert len(state.events) == 2
    assert state.events[0].success is True
    assert state.events[1].success is False
    assert state.events[1].data.get("error") == "timeout"


def test_state_save_load(tmp_path):
    state = make_state("https://example.com", keyword="test")
    state.raw_text = "Some content"

    path = tmp_path / "state.json"
    state.save(path)

    loaded = CrawlState.load(path)
    assert loaded.url == state.url
    assert loaded.raw_text == state.raw_text


def test_knowledge_crawl_tracking():
    k = Knowledge()
    assert not k.was_crawled("https://example.com")

    k.record_crawl("https://example.com")
    assert k.was_crawled("https://example.com")
    assert not k.was_crawled("https://other.com")


def test_knowledge_failure_tracking():
    k = Knowledge()
    k.record_failure("https://bad.com", "403 Forbidden")
    k.record_failure("https://bad.com", "403 Forbidden")

    assert k.failure_count("https://bad.com") == 2
    assert k.failure_count("https://good.com") == 0


def test_knowledge_prompt_stats():
    k = Knowledge()
    k.record_quality("prompts/rewrite.md", 80)
    k.record_quality("prompts/rewrite.md", 90)
    k.record_quality("prompts/rewrite.md", 70)

    stats = k.prompt_stats["prompts/rewrite.md"]
    assert stats.count == 3
    assert abs(stats.avg_score - 80.0) < 0.1


def test_knowledge_best_prompt():
    k = Knowledge()
    # Not enough samples for any prompt
    result = k.best_prompt_for("youtube", ["prompts/a.md", "prompts/b.md"])
    assert result == "prompts/a.md"  # fallback to first

    # Add enough samples
    for score in [90, 85, 88]:
        k.record_quality("prompts/b.md", score)

    result = k.best_prompt_for("youtube", ["prompts/a.md", "prompts/b.md"])
    assert result == "prompts/b.md"  # better avg


def test_knowledge_json_roundtrip(tmp_path):
    k = Knowledge()
    k.record_crawl("https://a.com")
    k.record_crawl("https://b.com")
    k.record_failure("https://c.com", "timeout")
    k.record_quality("prompts/test.md", 85)

    path = tmp_path / "knowledge.json"
    save_knowledge(k, path)

    loaded = load_knowledge(path)
    assert loaded.was_crawled("https://a.com")
    assert loaded.was_crawled("https://b.com")
    assert loaded.failure_count("https://c.com") == 1
    assert loaded.prompt_stats["prompts/test.md"].avg_score == 85.0


def test_last_verify_errors():
    state = make_state("https://example.com")
    assert state.last_verify_errors() == []

    state.append_event("verify", False, "Failed", issues=["Low quality", "Missing FAQ"])
    errors = state.last_verify_errors()
    assert "Low quality" in errors
    assert "Missing FAQ" in errors


def test_last_verify_errors_accumulates_across_attempts():
    """Errors from all verify failures should be accumulated, not just the latest."""
    state = make_state("https://example.com")

    # Attempt 1 fails
    state.append_event("verify", False, "Failed", issues=["Low quality", "Missing FAQ"])
    # Attempt 2 fails with different issues
    state.append_event(
        "verify", False, "Failed", issues=["Bad formatting", "Low quality"]
    )  # "Low quality" is duplicate

    errors = state.last_verify_errors()
    # Should have all unique errors, newest first
    assert "Bad formatting" in errors
    assert "Missing FAQ" in errors
    assert "Low quality" in errors
    # "Low quality" should appear only once (deduped)
    assert errors.count("Low quality") == 1


def test_events_capped_at_20():
    """Events list should be capped at 20 to prevent unbounded growth."""
    state = make_state("https://example.com")
    for i in range(25):
        state.append_event("test", True, f"event {i}")

    assert len(state.events) == 20
    # Should keep the most recent 20
    assert state.events[-1].message == "event 24"
    assert state.events[0].message == "event 5"


# --- Sprint 4: Reducer integration tests ---


def test_reducer_auto_skip_failed_urls():
    """Reducer should skip URLs that have failed 3+ times."""
    from knowledge import Knowledge
    from reducer import crawl

    state = make_state("https://always-fails.com", keyword="test")
    knowledge = Knowledge()
    # Simulate 3 previous failures
    knowledge.record_failure("https://always-fails.com", "403")
    knowledge.record_failure("https://always-fails.com", "403")
    knowledge.record_failure("https://always-failed.com", "403")

    # Also add the exact URL 3 times
    knowledge = Knowledge()
    for _ in range(3):
        knowledge.record_failure("https://always-fails.com", "timeout")

    from llm import LLM

    llm = LLM()
    result = crawl(state, knowledge, llm)

    assert result.step.value == "failed"
    assert "Auto-skipped" in result.error
    assert any(e.tool == "skip" for e in result.events)


def test_reducer_sets_preferred_extractor():
    """Reducer should set preferred_extractor when strategy is available."""
    from knowledge import Knowledge

    knowledge = Knowledge()
    for _ in range(5):
        knowledge.record_site_pattern("blog.example.com", "web", "prompts/rewrite.md", 85)

    strategy = knowledge.get_best_strategy("blog.example.com")
    assert strategy is not None
    extractor, prompt = strategy
    assert extractor == "web"

    # Verify state field works
    state = make_state("https://blog.example.com/post", keyword="test")
    state.preferred_extractor = extractor
    assert state.preferred_extractor == "web"
