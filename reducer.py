"""Reducer — the core crawl function (Factor #8 + #12).

This IS the control flow. No framework, no engine, no black box.
Just a function that takes state in, runs tools in order, returns state out.

The entire flow is readable in one function. That is the point.
"""

import logging
from pathlib import Path

from state import CrawlState, Step
from knowledge import Knowledge
from llm import LLM

from tools.extract import extract
from tools.rewrite import rewrite
from tools.seo import seo
from tools.render import render
from tools.verify import verify

logger = logging.getLogger("crawler.reducer")

MAX_FIX_ATTEMPTS = 2


def crawl(state: CrawlState, knowledge: Knowledge, llm: LLM) -> CrawlState:
    """The complete crawl pipeline — Factor #12: stateless reducer.
    
    Flow:
        extract → rewrite → seo → render → verify
                                              ↓ fail
                                          fix (rewrite + seo + render + verify, max 2x)
                                              ↓ still fail
                                          mark for human review
    """

    # Factor #13: Pre-fetch — check if already crawled
    if knowledge.was_crawled(state.url):
        logger.info(f"URL already crawled: {state.url}")
        state.append_event("skip", True, "Already crawled")
        return state

    # --- Step 1: Extract ---
    logger.info(f"[1/5] Extracting: {state.url}")
    state = extract(state)
    if state.error:
        return state

    # --- Step 2: Rewrite ---
    logger.info(f"[2/5] Rewriting: {state.keyword}")
    state = rewrite(state, llm, knowledge)
    if state.error:
        return state

    # --- Step 3: SEO ---
    logger.info(f"[3/5] SEO: {state.keyword}")
    state = seo(state, llm)
    if state.error:
        return state

    # --- Step 4: Render ---
    logger.info(f"[4/5] Rendering: {state.keyword}")
    state = render(state)
    if state.error:
        return state

    # --- Step 5: Verify + Fix loop (Factor #9) ---
    for attempt in range(MAX_FIX_ATTEMPTS + 1):
        logger.info(f"[5/5] Verifying (attempt {attempt + 1}): {state.keyword}")
        state = verify(state, llm)

        if state.verify and state.verify.passed:
            # Success!
            state.step = Step.PASSED
            knowledge.record_crawl(state.url)
            if state.verify:
                knowledge.record_quality("prompts/rewrite.md", state.verify.score)
            logger.info(f"PASSED: {state.keyword} (score={state.verify.score})")
            return state

        # Factor #9: Compact errors → inject into next rewrite context
        if attempt < MAX_FIX_ATTEMPTS:
            logger.info(f"Verification failed, fixing (attempt {attempt + 1}/{MAX_FIX_ATTEMPTS})")
            state.attempts = attempt + 1
            # Only rewrite + re-render, don't re-extract
            state = rewrite(state, llm, knowledge)
            state = seo(state, llm)
            state = render(state)
        else:
            # Factor #7: Contact human via tool call
            logger.warning(f"FAILED after {MAX_FIX_ATTEMPTS + 1} attempts: {state.keyword}")
            state.step = Step.FAILED
            state.error = f"Verification failed after {MAX_FIX_ATTEMPTS + 1} attempts"
            knowledge.record_failure(state.url, state.error)

    return state
