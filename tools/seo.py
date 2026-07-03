"""SEO tool - generate metadata (title, description, slug, h1).

Factor #4: LLM outputs structured JSON -> deterministic code uses it.
"""
import logging
from pathlib import Path

from state import CrawlState, SeoMetadata, Step
from llm import LLM
from context import build_seo_context
from tools.parse import parse_json

logger = logging.getLogger("crawler.seo")

_DEFAULT_SEO_PROMPT = """Generate SEO metadata for the given content. Return ONLY valid JSON.
{"title_tag":"SEO title (max 60 chars)","meta_description":"Meta desc (140-160 chars)","url_slug":"/category/slug","h1":"Main heading"}"""

_seo_prompt_cache: str | None = None


def _get_seo_prompt() -> str:
    """Lazy-load SEO prompt from file, with caching."""
    global _seo_prompt_cache
    if _seo_prompt_cache is None:
        prompt_path = Path(__file__).parent.parent / "prompts" / "seo.md"
        if prompt_path.exists():
            _seo_prompt_cache = prompt_path.read_text(encoding="utf-8")
        else:
            logger.warning("SEO prompt file not found at %s, using default", prompt_path)
            _seo_prompt_cache = _DEFAULT_SEO_PROMPT
    return _seo_prompt_cache


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
            system=_get_seo_prompt(),
            user=user_prompt,
            max_tokens=2048,
            temperature=0.3,
            cache_step="seo",
            cache_input=state.article_md[:300],
        )

        # Parse JSON from LLM response using shared parser
        metadata = parse_json(result)
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
