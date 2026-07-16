"""SEO metadata generation component."""
from __future__ import annotations
import json
import logging
import re
from pathlib import Path
from typing import Any

from ytarticle.core.base import BaseComponent
from ytarticle.core.schema import ContentItem
from ytarticle.support.llm import call_llm

logger = logging.getLogger("ytarticle.seo_metadata")

# Built-in default prompt (used when prompt_file is not configured)
SEO_PROMPT = """You are an SEO specialist. Given the article, generate metadata in valid JSON:
{
    "title_tag": "Title | SiteName (max 65 chars)",
    "meta_description": "Description (max 155 chars)",
    "url_slug": "/diy/kebab-case-slug",
    "h1": "Main heading"
}
Output ONLY the JSON object."""


def _load_prompt(config: dict[str, Any], default: str) -> str:
    """Load prompt from external file if configured."""
    prompt_file = config.get("prompt_file", "")
    if prompt_file:
        p = Path(prompt_file)
        if p.exists():
            return p.read_text(encoding="utf-8")
        logger.warning(f"[seo_metadata] prompt_file not found: {prompt_file}, using default")
    return default


class SeoMetadata(BaseComponent):
    name = "seo_metadata"
    version = "1.0.0"
    required_fields = ["article_md"]
    output_fields = ["seo"]

    def run(self, item: ContentItem, config: dict[str, Any]) -> ContentItem:
        article_excerpt = item.article_md[:3000]
        site_name = config.get("site_name", "MakeDIYHub")
        prompt = _load_prompt(config, SEO_PROMPT)

        user_prompt = f"Site: {site_name}\n\nArticle excerpt:\n{article_excerpt}"
        logger.info(f"[seo_metadata] Generating SEO metadata...")
        result = call_llm(prompt, user_prompt, max_tokens=1024, temperature=0.3)

        json_match = re.search(r"\{.*\}", result, re.DOTALL)
        if json_match:
            try:
                seo_data = json.loads(json_match.group())
            except json.JSONDecodeError:
                seo_data = {}
        else:
            seo_data = {}

        raw_title = seo_data.get("title_tag", item.title)
        # Fix unclosed brackets: " [Tested" → " [Tested]"
        if raw_title.count("[") > raw_title.count("]"):
            raw_title += "]"
        item.seo.title_tag = self._truncate_title(raw_title, site_name)
        item.seo.meta_description = seo_data.get("meta_description", "")[:155]
        # Fallback: generate description from article content if LLM returned empty
        if not item.seo.meta_description.strip():
            item.seo.meta_description = item.article_md[:200].replace("\n", " ").replace("#", "").strip()[:155]
        item.seo.url_slug = seo_data.get("url_slug", f"/diy/{item.source_id}")
        item.seo.h1 = seo_data.get("h1", item.title)
        return item

    @staticmethod
    def _truncate_title(title: str, site_name: str) -> str:
        suffix = f" | {site_name}"
        # Strip existing suffix if LLM already added it
        if title.endswith(suffix):
            title = title[:-len(suffix)]
        elif title.endswith(f" | {site_name[:6]}"):
            # LLM truncated the suffix partially — strip it
            sep = title.rfind(" | ")
            if sep > 0:
                title = title[:sep]
        max_len = 70
        if len(title) + len(suffix) <= max_len:
            return title + suffix
        space = max_len - len(suffix)
        if space > 10:
            trimmed = title[:space].rstrip()
            # Don't leave an unclosed bracket tag
            if trimmed.count("[") > trimmed.count("]"):
                bracket_pos = trimmed.rfind("[")
                if bracket_pos > 0:
                    trimmed = trimmed[:bracket_pos].rstrip()
            return trimmed + suffix
        return title[:max_len - 3].rstrip() + "..."


def create():
    return SeoMetadata()
