"""Tests for keyword coverage tracking."""
from knowledge import Knowledge, KeywordCoverage


def test_record_keyword_coverage():
    """Should record keyword as covered after successful crawl."""
    k = Knowledge()
    k.record_coverage("hiking tips", "https://a.com/article", score=85)
    assert "hiking tips" in k.keyword_coverage
    cov = k.keyword_coverage["hiking tips"]
    assert cov.covered is True
    assert cov.article_url == "https://a.com/article"
    assert cov.score == 85


def test_coverage_summary():
    """Should return covered/uncovered counts."""
    k = Knowledge()
    k.record_coverage("hiking tips", "https://a.com", score=85)
    k.record_coverage("camping gear", "https://b.com", score=72)
    k.add_target_keyword("backpacking")

    summary = k.coverage_summary()
    assert summary["covered"] == 2
    assert summary["targeted"] == 1
    assert summary["total_keywords"] == 3


def test_add_target_keyword():
    """Adding a target keyword should mark it as uncovered."""
    k = Knowledge()
    k.add_target_keyword("python tutorial")
    assert "python tutorial" in k.keyword_coverage
    assert k.keyword_coverage["python tutorial"].covered is False


def test_coverage_not_duplicated():
    """Recording same keyword twice should update, not duplicate."""
    k = Knowledge()
    k.record_coverage("hiking", "https://a.com", score=80)
    k.record_coverage("hiking", "https://b.com", score=90)
    assert len(k.keyword_coverage) == 1
    assert k.keyword_coverage["hiking"].score == 90


def test_coverage_json_roundtrip():
    """Coverage should survive JSON serialization."""
    import tempfile, os
    from knowledge import save_knowledge, load_knowledge

    k = Knowledge()
    k.record_coverage("test", "https://a.com", score=80)
    k.add_target_keyword("uncovered")

    path = tempfile.mktemp(suffix=".json")
    save_knowledge(k, path)
    k2 = load_knowledge(path)
    os.unlink(path)

    assert "test" in k2.keyword_coverage
    assert k2.keyword_coverage["test"].covered is True
    assert k2.keyword_coverage["test"].score == 80
    assert "uncovered" in k2.keyword_coverage
    assert k2.keyword_coverage["uncovered"].covered is False
