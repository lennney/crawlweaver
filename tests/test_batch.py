"""Tests for batch CSV import."""
import tempfile
import os


def test_parse_csv():
    """Should parse CSV with url, keyword, source columns."""
    from cli import parse_batch_csv

    csv_content = "url,keyword,source\nhttps://a.com,test a,web\nhttps://b.com,test b,youtube\n"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write(csv_content)
        f.flush()
        rows = parse_batch_csv(f.name)
    os.unlink(f.name)

    assert len(rows) == 2
    assert rows[0]["url"] == "https://a.com"
    assert rows[0]["keyword"] == "test a"
    assert rows[0]["source"] == "web"
    assert rows[1]["source"] == "youtube"


def test_parse_csv_defaults():
    """Missing source/content_type should use defaults."""
    from cli import parse_batch_csv

    csv_content = "url,keyword\nhttps://a.com,test\n"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write(csv_content)
        f.flush()
        rows = parse_batch_csv(f.name)
    os.unlink(f.name)

    assert rows[0]["source"] == "youtube"
    assert rows[0]["content_type"] == "Beginner Guide"


def test_parse_csv_empty():
    """Empty CSV should return empty list."""
    from cli import parse_batch_csv

    csv_content = "url,keyword\n"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write(csv_content)
        f.flush()
        rows = parse_batch_csv(f.name)
    os.unlink(f.name)

    assert rows == []
