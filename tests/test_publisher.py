"""Tests for static site publisher."""

from publisher import generate_site


def test_generate_site(tmp_path):
    """Should generate index.html + copy articles."""
    # Setup: create mock output articles
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "test-article.html").write_text("<html><body><h1>Test</h1></body></html>")
    (output_dir / "another-post.html").write_text("<html><body><h1>Another</h1></body></html>")

    site_dir = tmp_path / "site"
    generate_site(output_dir=output_dir, site_dir=site_dir, title="My Content Hub")

    assert (site_dir / "index.html").exists()
    assert (site_dir / "test-article.html").exists()
    assert (site_dir / "another-post.html").exists()
    index = (site_dir / "index.html").read_text()
    assert "My Content Hub" in index
    assert "test-article.html" in index


def test_generate_rss(tmp_path):
    """Should generate RSS feed."""
    from publisher import generate_rss

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "post.html").write_text("<html><body><h1>Post</h1></body></html>")

    site_dir = tmp_path / "site"
    site_dir.mkdir()
    generate_rss(
        output_dir=output_dir, site_dir=site_dir, title="Feed", base_url="https://example.com"
    )

    rss_path = site_dir / "feed.xml"
    assert rss_path.exists()
    content = rss_path.read_text()
    assert "<rss" in content
    assert "Post" in content
