"""Rewrite tool — AI-powered content rewriting.

Factor #1: NL → tool calls (LLM generates structured article).
Factor #2: Own prompts (loads from prompts/ directory).
Factor #3: Own context (context.py decides what LLM sees).
Factor #4: Tools are structured outputs (parse LLM response as article).
"""

import logging
import re
from pathlib import Path

from state import CrawlState, Step
from llm import LLM
from context import build_rewrite_context
from knowledge import Knowledge
from tools.parse import parse_llm_output

logger = logging.getLogger("crawler.rewrite")

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def rewrite(state: CrawlState, llm: LLM, knowledge: Knowledge) -> CrawlState:
    """Rewrite raw content into an SEO article."""
    if not state.raw_text:
        state.error = "No raw_text to rewrite"
        state.append_event("rewrite", False, "No raw_text")
        return state

    try:
        # Factor #13: Pre-fetch — pick best prompt based on history
        prompt_candidates = [
            str(PROMPTS_DIR / "rewrite.md"),
        ]
        prompt_path = knowledge.best_prompt_for(state.source.value, prompt_candidates)
        system_prompt = Path(prompt_path).read_text(encoding="utf-8")

        # Factor #3: Context engineering — code decides what LLM sees
        user_prompt = build_rewrite_context(state, knowledge)

        logger.info(f"Rewriting '{state.keyword}' ({len(state.raw_text)} chars raw, attempt={state.attempts})")
        # Bug fix: include attempt in cache key so fix loops don't return stale cached rewrites
        cache_suffix = f"_fix{state.attempts}" if state.attempts > 0 else ""
        result = parse_llm_output(llm.call(
            system=system_prompt,
            user=user_prompt,
            max_tokens=8192,
            temperature=0.7,
            cache_step=f"rewrite{cache_suffix}",
            cache_input=state.raw_text[:500],
        ))

        # Parse result — extract title and body
        state.article_md = result
        # Try to extract H1 as title
        h1 = re.search(r"^#\s+(.+)$", result, re.MULTILINE)
        state.title = h1.group(1) if h1 else state.title

        state.step = Step.REWRITTEN
        state.append_event("rewrite", True, f"Generated {len(result)} chars")
        logger.info(f"Rewrite done: {len(result)} chars")

    except Exception as e:
        state.error = str(e)
        state.append_event("rewrite", False, str(e))
        logger.error(f"Rewrite failed: {e}")

    return state
