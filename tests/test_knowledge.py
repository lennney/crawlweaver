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
