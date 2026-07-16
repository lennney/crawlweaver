"""AI rewrite — transforms raw transcript into structured article."""
from __future__ import annotations
import logging
import os
import re
from pathlib import Path
from typing import Any

from ytarticle.core.base import BaseComponent
from ytarticle.core.schema import ContentItem
from ytarticle.support.llm import call_llm

logger = logging.getLogger("ytarticle.ai_rewrite")

# Built-in default prompt (used when prompt_file is not configured)
REWRITE_PROMPT = """You are a DIY article writer. Transform the YouTube transcript into a 
step-by-step tutorial article.

Output format:
<!-- METADATA
title: Article H1 Title
difficulty: easy|medium|hard
time: X minutes/hours
cost: $X
materials: item1, item2, item3
-->
## Introduction
[2-3 sentences]

## Step-by-Step
### Step 1: [Title]
[detailed instructions]

### Step 2: [Title]
[detailed instructions]
...

## Tips & Tricks
[2-3 tips]
"""


def _load_prompt(config: dict[str, Any], default: str) -> str:
    """Load prompt from external file if configured, else return default."""
    prompt_file = config.get("prompt_file", "")
    if prompt_file:
        p = Path(prompt_file)
        if p.exists():
            return p.read_text(encoding="utf-8")
        logger.warning(f"[ai_rewrite] prompt_file not found: {prompt_file}, using default")
    return default


class AIRewrite(BaseComponent):
    name = "ai_rewrite"
    version = "1.0.0"
    required_fields = ["raw_text", "title"]
    output_fields = ["article_md", "difficulty", "estimated_time", "estimated_cost", "materials"]

    def run(self, item: ContentItem, config: dict[str, Any]) -> ContentItem:
        system_prompt = _load_prompt(config, REWRITE_PROMPT)
        user_prompt = f"Title: {item.title}\n\nTranscript:\n{item.raw_text}"

        logger.info(f"[ai_rewrite] Generating article...")
        article = call_llm(system_prompt, user_prompt, max_tokens=8192)

        meta = self._parse_metadata(article)
        item.difficulty = meta.get("difficulty", "medium")
        item.estimated_time = meta.get("time", "")
        item.estimated_cost = meta.get("cost", "")
        materials_raw = meta.get("materials", "")
        if "," in materials_raw:
            item.materials = [m.strip() for m in materials_raw.split(",") if m.strip()]
        else:
            item.materials = [re.sub(r"^[-*•]\s*", "", m.strip())
                             for m in materials_raw.split("\n") if m.strip()]

        item.article_md = self._strip_metadata(article)

        # Save markdown to disk
        output_dir = Path(config.get("output_dir", "output/articles"))
        output_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", item.title.lower()).strip("-")[:60]
        md_path = output_dir / f"{item.source_id}-{slug}.md"
        md_path.write_text(item.article_md, encoding="utf-8")
        item.artifacts.article_md = str(md_path)
        logger.info(f"[ai_rewrite] Saved article to {md_path}")

        return item

    @staticmethod
    def _parse_metadata(article: str) -> dict:
        m = re.search(r"<!-- METADATA(.*?)-->", article, re.DOTALL)
        if not m:
            return {}
        meta = {}
        for line in m.group(1).strip().split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip()
        return meta

    @staticmethod
    def _strip_metadata(article: str) -> str:
        return re.sub(r"<!-- METADATA.*?-->", "", article, flags=re.DOTALL).strip()


def create():
    return AIRewrite()
