"""Tests for core schema and pipeline."""
import pytest
from ytarticle.core.schema import ContentItem, ImageInfo, SeoMetadata, make_item, Source
from ytarticle.core.pipeline import Pipeline

class TestContentItem:
    def test_make_item_youtube(self):
        item = make_item("youtube", "abc123")
        assert item.source == Source.YOUTUBE
        assert item.source_id == "abc123"
        assert item.status == "pending"

    def test_mark_done(self):
        item = make_item("youtube", "test")
        item.mark_done()
        assert item.status == "done"
        assert item.completed_at != ""

    def test_mark_failed(self):
        item = make_item("youtube", "test")
        item.mark_failed("Something broke")
        assert item.status == "failed"
        assert item.error == "Something broke"

    def test_image_info(self):
        img = ImageInfo(path="/tmp/step_01.jpg", alt="Step 1", step=1)
        assert img.step == 1
        assert "step_01" in img.path

    def test_seo_metadata(self):
        seo = SeoMetadata(title_tag="DIY Guide | MakeDIYHub", meta_description="A guide.", url_slug="/diy/test")
        assert "MakeDIYHub" in seo.title_tag
        assert seo.url_slug.startswith("/diy/")

class TestPipeline:
    def test_invalid_component(self):
        config = {"steps": [{"component": "nonexistent", "id": "test", "config": {}}]}
        pipe = Pipeline(config)
        item = make_item("youtube", "test")
        result = pipe.run(item)
        assert result.status == "failed"
        assert "not found" in result.error.lower()

    def test_missing_required_fields(self, tmp_path):
        config = {
            "steps": [{"component": "ai_rewrite", "id": "rewrite", "config": {}}]
        }
        pipe = Pipeline(config)
        item = make_item("youtube", "test")
        result = pipe.run(item)
        assert result.status == "failed"