"""Tests for knowledge module - site patterns and failure reports."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from knowledge import Knowledge, SitePattern


def test_record_site_pattern():
    knowledge = Knowledge()
    knowledge.record_site_pattern(
        domain="youtube.com", extractor="youtube",
        prompt="prompts/rewrite.md", quality=85,
    )
    assert "youtube.com" in knowledge.site_patterns
    sp = knowledge.site_patterns["youtube.com"]
    assert sp.extractor == "youtube"
    assert sp.sample_count == 1
    assert sp.avg_quality == 85.0


def test_record_site_pattern_updates_avg():
    knowledge = Knowledge()
    knowledge.record_site_pattern("youtube.com", "youtube", "prompts/rewrite.md", 80)
    knowledge.record_site_pattern("youtube.com", "youtube", "prompts/rewrite.md", 90)
    sp = knowledge.site_patterns["youtube.com"]
    assert sp.sample_count == 2
    assert sp.avg_quality == 85.0


def test_site_pattern_has_total_quality():
    """SitePattern should have total_quality accumulator."""
    sp = SitePattern(extractor="web", best_prompt="p.md", avg_quality=80.0, sample_count=1, total_quality=80.0)
    assert sp.total_quality == 80.0


def test_failure_report_field():
    """CrawlState should have failure_report field."""
    from state import make_state
    state = make_state("https://example.com", keyword="test")
    assert state.failure_report is None
    state.failure_report = {"url": "https://example.com", "error": "test"}
    assert state.failure_report["error"] == "test"


# --- Sprint 4: Knowledge self-evolution tests ---

def test_get_best_strategy_enough_samples():
    """get_best_strategy returns (extractor, prompt) when sample_count >= 3."""
    k = Knowledge()
    k.record_site_pattern("blog.example.com", "web", "prompts/rewrite.md", 85)
    k.record_site_pattern("blog.example.com", "web", "prompts/rewrite.md", 90)
    k.record_site_pattern("blog.example.com", "web", "prompts/rewrite.md", 88)

    result = k.get_best_strategy("blog.example.com")
    assert result is not None
    extractor, prompt = result
    assert extractor == "web"
    assert prompt == "prompts/rewrite.md"


def test_get_best_strategy_not_enough_samples():
    """get_best_strategy returns None when sample_count < 3."""
    k = Knowledge()
    k.record_site_pattern("newsite.com", "web", "prompts/rewrite.md", 80)
    k.record_site_pattern("newsite.com", "web", "prompts/rewrite.md", 75)

    assert k.get_best_strategy("newsite.com") is None


def test_get_best_strategy_unknown_domain():
    """get_best_strategy returns None for unknown domains."""
    k = Knowledge()
    assert k.get_best_strategy("unknown.com") is None


def test_get_best_strategy_no_extractor():
    """get_best_strategy returns None when extractor is empty."""
    k = Knowledge()
    k.site_patterns["empty.com"] = SitePattern(
        extractor="", best_prompt="p.md", avg_quality=80.0,
        sample_count=5, total_quality=400.0,
    )
    assert k.get_best_strategy("empty.com") is None


def test_should_skip_threshold():
    """should_skip returns True when failure_count >= max_failures."""
    k = Knowledge()
    k.record_failure("https://bad.com", "403")
    k.record_failure("https://bad.com", "403")
    assert not k.should_skip("https://bad.com")  # 2 < 3 default

    k.record_failure("https://bad.com", "403")
    assert k.should_skip("https://bad.com")  # 3 >= 3


def test_should_skip_custom_threshold():
    """should_skip respects custom max_failures."""
    k = Knowledge()
    k.record_failure("https://flaky.com", "timeout")
    assert k.should_skip("https://flaky.com", max_failures=1)
    assert not k.should_skip("https://flaky.com", max_failures=5)


def test_should_skip_different_errors():
    """should_skip counts ALL failures regardless of error type."""
    k = Knowledge()
    k.record_failure("https://bad.com", "403")
    k.record_failure("https://bad.com", "timeout")
    k.record_failure("https://bad.com", "500")
    assert k.should_skip("https://bad.com")  # 3 total, even though errors differ


def test_should_skip_unknown_url():
    """should_skip returns False for URLs with no failures."""
    k = Knowledge()
    assert not k.should_skip("https://never-failed.com")


def test_preferred_extractor_field():
    """CrawlState has preferred_extractor field."""
    from state import make_state
    state = make_state("https://example.com", keyword="test")
    assert state.preferred_extractor == ""
    state.preferred_extractor = "web"
    assert state.preferred_extractor == "web"
