"""Tests for pipeline components."""
import os
import json
from pathlib import Path
import pytest
from ytarticle.core.schema import ContentItem, ImageInfo, make_item, SeoMetadata
from ytarticle.components.processors.convert_webp import ConvertWebP
from ytarticle.components.checkers.content_check import ContentCheck
from ytarticle.components.processors.html_render import HtmlRender

class TestConvertWebP:
    def test_no_images(self):
        comp = ConvertWebP()
        item = make_item("youtube", "test")
        result = comp.run(item, {"quality": 85})
        assert result is item  # no-op

    def test_with_images_preserves_webp(self):
        comp = ConvertWebP()
        item = make_item("youtube", "test")
        img = ImageInfo(path="/tmp/fake_01.webp", alt="Step", step=1)
        item.images = [img]
        result = comp.run(item, {"quality": 85})
        assert result.images[0].path == "/tmp/fake_01.webp"  # unchanged

class TestContentCheck:
    def test_passes_valid_article(self):
        comp = ContentCheck()
        item = make_item("youtube", "test")
        item.article_md = "This is a test article " * 30  # ~120 words
        item.seo = SeoMetadata(
            title_tag="My DIY Guide | MakeDIYHub",
            meta_description="A great DIY guide for testing purposes with enough length to pass checks",
            url_slug="/diy/test",
            h1="My DIY Guide"
        )
        result = comp.run(item, {})
        warnings = result.source_metadata.get("check_warnings", [])
        assert len(warnings) == 0

    def test_warns_short_article(self):
        comp = ContentCheck()
        item = make_item("youtube", "test")
        item.article_md = "short"
        item.seo = SeoMetadata(title_tag="Test | MakeDIYHub")
        result = comp.run(item, {})
        warnings = result.source_metadata.get("check_warnings", [])
        assert any("too short" in w.lower() for w in warnings)

class TestHtmlRender:
    def test_parse_cost(self):
        render = HtmlRender()
        assert render._parse_cost("$5-$15") == {"@type": "MonetaryAmount", "currency": "USD", "minValue": "5", "maxValue": "15"}
        assert render._parse_cost("£10") == {"@type": "MonetaryAmount", "currency": "GBP", "value": "10"}
        assert render._parse_cost("free") is None

    def test_parse_time_iso(self):
        render = HtmlRender()
        assert render._parse_time_iso("1-2 hours") == "PT2H"
        assert render._parse_time_iso("30 minutes") == "PT30M"
        assert render._parse_time_iso("1.5 hours") == "PT1H30M"
        assert render._parse_time_iso("") is None

    def test_render_basic(self, tmp_path):
        render = HtmlRender()
        # Use the built-in diyhub template via resolve_template custom_dirs
        from ytarticle.templates.base import resolve_template
        template_dir, resolved_name = resolve_template("diyhub/article.html")

        item = make_item("youtube", "test123")
        item.title = "Test Article"
        item.article_md = "## Introduction\nThis is a test.\n## Step-by-Step\n### Step 1: Do it\nThe first step."
        item.seo = SeoMetadata(
            title_tag="Test Article | MakeDIYHub",
            meta_description="A test article for rendering",
            url_slug="/diy/test",
            h1="Test Article"
        )
        item.artifacts.cover_img = "https://example.com/cover.jpg"

        config = {"template": "diyhub/article.html", "output_dir": str(tmp_path),
                  "site_url": "https://test.com", "site_name": "Test"}
        result = render.run(item, config)
        assert result.artifacts.html_path
        assert Path(result.artifacts.html_path).exists()

class TestAIREWrite:
    def test_parse_metadata(self):
        from ytarticle.components.processors.ai_rewrite import AIRewrite
        article = """<!-- METADATA
difficulty: easy
time: 2 hours
cost: $10-$20
materials: wood, glue, paint
-->
## Introduction
Test content."""
        meta = AIRewrite._parse_metadata(article)
        assert meta["difficulty"] == "easy"
        assert meta["time"] == "2 hours"
        assert meta["cost"] == "$10-$20"