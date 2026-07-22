"""Reducer - the core crawl function (Factor #8 + #12).

This IS the control flow. No framework, no engine, no black box.
Just a function that takes state in, runs tools in order, returns state out.

The entire flow is readable in one function. That is the point.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from knowledge import Knowledge
from llm import LLM
from state import CrawlState, Step
from tools.extract import extract
from tools.render import render
from tools.rewrite import rewrite
from tools.seo import seo
from tools.verify import verify

logger = logging.getLogger("crawler.reducer")

MAX_FIX_ATTEMPTS = 2


def crawl(
    state: CrawlState, knowledge: Knowledge, llm: LLM, state_path: str | None = None
) -> CrawlState:
    """The complete crawl pipeline - Factor #12: stateless reducer.

    Flow:
        extract -> rewrite -> seo -> render -> verify
                                              | fail
                                          fix (rewrite + seo + render + verify, max 2x)
                                              | still fail
                                          mark for human review
    """

    def _checkpoint():
        """Factor #6: auto-save state after each step (WAL mode)."""
        if state_path:
            try:
                state.save(state_path)
            except Exception as e:
                logger.warning(f"WAL checkpoint failed: {e}")

    # Factor #13: Pre-fetch - check if already crawled
    if knowledge.was_crawled(state.url):
        logger.info(f"URL already crawled: {state.url}")
        state.append_event("skip", True, "Already crawled")
        _checkpoint()
        return state

    # Sprint 4: Auto-skip URLs with repeated failures
    if knowledge.should_skip(state.url):
        fail_count = knowledge.failure_count(state.url)
        logger.warning(f"URL failed {fail_count} times, skipping: {state.url}")
        state.step = Step.FAILED
        state.error = f"Auto-skipped: {fail_count} previous failures"
        state.append_event("skip", True, f"Failed {fail_count}x before")
        _checkpoint()
        return state

    # Sprint 4: Knowledge-guided extraction strategy
    domain = urlparse(state.url).netloc
    strategy = knowledge.get_best_strategy(domain)
    if strategy:
        extractor, prompt = strategy
        state.preferred_extractor = extractor
        logger.info(f"Using learned strategy for {domain}: extractor={extractor}")

    # Cost tracking: collect CostRecord after each LLM step
    cost_records: list = []

    # --- Step 1: Extract ---
    logger.info(f"[1/5] Extracting: {state.url}")
    state = extract(state)
    _checkpoint()
    if state.error:
        return state

    # --- Step 2: Rewrite ---
    logger.info(f"[2/5] Rewriting: {state.keyword}")
    state = rewrite(state, llm, knowledge)
    if llm.last_cost:
        cost_records.append(llm.last_cost)
    _checkpoint()
    if state.error:
        return state

    # --- Step 3: SEO ---
    logger.info(f"[3/5] SEO: {state.keyword}")
    state = seo(state, llm)
    if llm.last_cost:
        cost_records.append(llm.last_cost)
    _checkpoint()
    if state.error:
        return state

    # --- Step 4: Render ---
    logger.info(f"[4/5] Rendering: {state.keyword}")
    state = render(state)
    _checkpoint()
    if state.error:
        return state

    # --- Step 5: Verify + Fix loop (Factor #9) ---
    for attempt in range(MAX_FIX_ATTEMPTS + 1):
        logger.info(f"[5/5] Verifying (attempt {attempt + 1}): {state.keyword}")
        state = verify(state, llm)
        if llm.last_cost:
            cost_records.append(llm.last_cost)
        _checkpoint()

        if state.verify and state.verify.passed:
            # Success — move to REVIEW for human approval
            state.step = Step.REVIEW
            knowledge.record_crawl(state.url)
            if state.verify:
                knowledge.record_quality("prompts/rewrite.md", state.verify.score)
            # Factor #13: record site pattern
            domain = urlparse(state.url).netloc
            knowledge.record_site_pattern(
                domain=domain,
                extractor=state.source.value,
                prompt="prompts/rewrite.md",
                quality=state.verify.score,
            )
            # Record keyword coverage
            if state.keyword:
                knowledge.record_coverage(
                    keyword=state.keyword,
                    article_url=state.html_path or state.url,
                    score=state.verify.score if state.verify else 0,
                )
            # Record article cost
            if cost_records:
                knowledge.record_article_cost(
                    url=state.url,
                    keyword=state.keyword,
                    cost_records=cost_records,
                )
            _checkpoint()
            logger.info(f"PASSED: {state.keyword} (score={state.verify.score})")
            return state

        # Factor #9: Compact errors -> inject into next rewrite context
        if attempt < MAX_FIX_ATTEMPTS:
            logger.info(f"Verification failed, fixing (attempt {attempt + 1}/{MAX_FIX_ATTEMPTS})")
            state.attempts = attempt + 1
            # Only rewrite + re-render, don't re-extract
            state = rewrite(state, llm, knowledge)
            if llm.last_cost:
                cost_records.append(llm.last_cost)
            state = seo(state, llm)
            if llm.last_cost:
                cost_records.append(llm.last_cost)
            state = render(state)
            _checkpoint()
        else:
            # Factor #7: Set structured failure report
            logger.warning(f"FAILED after {MAX_FIX_ATTEMPTS + 1} attempts: {state.keyword}")
            state.step = Step.FAILED
            state.error = f"Verification failed after {MAX_FIX_ATTEMPTS + 1} attempts"
            state.failure_report = {
                "url": state.url,
                "keyword": state.keyword,
                "error": state.error,
                "step": state.step.value,
                "attempts": state.attempts,
            }
            knowledge.record_failure(state.url, state.error)
            _checkpoint()

    return state
