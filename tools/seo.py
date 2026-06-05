"""SEO tool — generate metadata (title, description, slug, h1).

Factor #4: LLM outputs structured JSON → deterministic code uses it.
"""

import json
import logging
import re
from pathlib import Path

from state import CrawlState, SeoMetadata, Step
from llm import LLM
from context import build_seo_context

logger = logging.getLogger("crawler.seo")

SEO_PROMPT = (Path(__file__).parent.parent / "prompts" / "seo.md").read_text(encoding="utf-8")     if (Path(__file__).parent.parent / "prompts" / "seo.md").exists() else     """Generate SEO metadata for the given content. Return ONLY valid JSON.
{"title_tag":"SEO title (max 60 chars)","meta_description":"Meta desc (140-160 chars)","url_slug":"/category/slug","h1":"Main heading"}"""


def seo(state: CrawlState, llm: LLM) -> CrawlState:
    """Generate SEO metadata from the rewritten article."""
    if not state.article_md:
        state.error = "No article_md for SEO"
        state.append_event("seo", False, "No article_md")
        return state

    try:
        user_prompt = build_seo_context(state)

        logger.info(f"Generating SEO for '{state.keyword}'")
        result = llm.call(
            system=SEO_PROMPT,
            user=user_prompt,
            max_tokens=512,
            temperature=0.3,
            cache_step="seo",
            cache_input=state.article_md[:300],
        )

        # Parse JSON from LLM response
        metadata = _parse_json(result)
        state.seo = SeoMetadata(
            title_tag=metadata.get("title_tag", "")[:60],
            meta_description=metadata.get("meta_description", "")[:160],
            url_slug=metadata.get("url_slug", ""),
            h1=metadata.get("h1", ""),
        )

        state.step = Step.SEO_DONE
        state.append_event("seo", True, f"Title: {state.seo.title_tag}")
        logger.info(f"SEO done: {state.seo.title_tag}")

    except Exception as e:
        state.error = str(e)
        state.append_event("seo", False, str(e))
        logger.error(f"SEO failed: {e}")

    return state


def _parse_json(text: str) -> dict:
    """Extract JSON from LLM response (handles markdown code blocks)."""
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from code block
    m = re.search(r"```(?:json)?\s*\n?(.+?)\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding first { to last }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Cannot parse JSON from LLM response: {text[:200]}")
