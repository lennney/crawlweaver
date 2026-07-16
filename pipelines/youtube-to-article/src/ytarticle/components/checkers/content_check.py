"""Content quality checker — validates HTML and SEO metadata."""
from __future__ import annotations
import logging
import re
from pathlib import Path
from typing import Any

from ytarticle.core.base import BaseComponent
from ytarticle.core.schema import ContentItem

logger = logging.getLogger("ytarticle.content_check")


class ContentCheck(BaseComponent):
    name = "content_check"
    version = "2.0.0"
    required_fields = ["article_md", "seo"]
    output_fields: list[str] = []

    def run(self, item: ContentItem, config: dict[str, Any]) -> ContentItem:
        warnings = self._check_seo(item) + self._check_html(item)

        if warnings:
            logger.warning(f"[content_check] {len(warnings)} warnings:")
            for w in warnings:
                logger.warning(f"  ⚠ {w}")
        else:
            logger.info("[content_check] All checks passed")

        item.source_metadata["check_warnings"] = warnings
        return item

    def _check_seo(self, item: ContentItem) -> list[str]:
        warnings = []
        tag = item.seo.title_tag or ""
        if len(tag) > 65:
            warnings.append(f"title_tag too long: {len(tag)} chars (max 65)")
        elif not tag:
            warnings.append("title_tag is empty")

        desc = item.seo.meta_description or ""
        if len(desc) > 155:
            warnings.append(f"meta_description too long: {len(desc)} chars (max 155)")
        elif not desc:
            warnings.append("meta_description is empty")

        slug = item.seo.url_slug or ""
        if not slug:
            warnings.append("url_slug is empty")

        h1 = item.seo.h1 or item.title
        if not h1:
            warnings.append("h1 is empty")

        word_count = len(item.article_md.split())
        if word_count < 100:
            warnings.append(f"Article too short: {word_count} words (min 100)")

        if item.difficulty not in ("easy", "medium", "hard", "Easy", "Medium", "Hard"):
            if item.difficulty:
                warnings.append(f"Unknown difficulty: {item.difficulty}")

        return warnings

    def _check_html(self, item: ContentItem) -> list[str]:
        warnings = []
        html_path = item.artifacts.html_path
        if not html_path:
            return warnings

        path = Path(html_path)
        if not path.exists():
            warnings.append("HTML file not found")
            return warnings

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ["File is not valid UTF-8"]

        if "" in text:
            warnings.append("Contains Unicode replacement characters (U+FFFD)")

        if "\x00" in text:
            warnings.append("Contains null bytes")

        # Check for critical schema.org markup
        for schema_type in ["HowTo", "BreadcrumbList"]:
            if schema_type not in text:
                warnings.append(f"Missing {schema_type} schema.org markup")

        # Check for step images
        imgs = re.findall(r'<img[^>]+src="([^"]+)"', text)
        step_imgs = [i for i in imgs if "step_" in i]
        if not step_imgs and not any("maxresdefault" in i or "hqdefault" in i for i in imgs):
            warnings.append("No step images found in HTML")

        return warnings


def create():
    return ContentCheck()