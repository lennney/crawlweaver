"""Verify tool - AI-powered quality check (Factor #9: Compact errors).

5-dimension scoring. Failures become compact error messages
that get injected back into rewrite context for self-healing.
"""
import logging
from datetime import datetime
from pathlib import Path

from state import CrawlState, Step, VerifyResult
from llm import LLM
from context import build_verify_context
from tools.parse import parse_json

logger = logging.getLogger("crawler.verify")

VERIFY_PROMPT = """Score this article (0-20 each, total 0-100):
1. Accuracy: facts traceable to source?
2. Completeness: core info covered? word count met?
3. SEO: title/description include keyword? structure good?
4. Readability: paragraphs reasonable? language natural?
5. Compliance: no risky content? source attribution?

Output JSON only. IMPORTANT: "issues" and "fix_suggestions" must be arrays of plain strings, NOT objects.

{"score":85,"dimensions":{"accuracy":{"score":18},"completeness":{"score":16},"seo":{"score":17},"readability":{"score":17},"compliance":{"score":17}},"issues":["issue description"],"fix_suggestions":["suggestion"]}"""


def verify(state: CrawlState, llm: LLM, min_score: int = 70) -> CrawlState:
    """Verify article quality. Sets state.verify with result."""
    if not state.article_md:
        state.error = "No article_md to verify"
        state.append_event("verify", False, "No article_md")
        return state

    try:
        user_prompt = build_verify_context(state)

        logger.info(f"Verifying '{state.keyword}' (min_score={min_score})")
        result = llm.call(
            system=VERIFY_PROMPT,
            user=user_prompt,
            max_tokens=4096,
            temperature=0.3,
        )

        parsed = _parse_verify_json(result)
        parsed["checked_at"] = datetime.now().isoformat()
        parsed["passed"] = parsed.get("score", 0) >= min_score

        verify_result = VerifyResult(**parsed)
        state.verify = verify_result

        if verify_result.passed:
            state.step = Step.PASSED
            state.append_event("verify", True,
                               f"PASSED score={verify_result.score}",
                               score=verify_result.score)
        else:
            state.step = Step.VERIFIED
            state.append_event("verify", False,
                               f"FAILED score={verify_result.score}",
                               score=verify_result.score,
                               issues=verify_result.issues,
                               fix_suggestions=verify_result.fix_suggestions)

        logger.info(f"Verify: score={verify_result.score} passed={verify_result.passed}")

    except Exception as e:
        state.error = str(e)
        state.append_event("verify", False, str(e))
        logger.error(f"Verify failed: {e}")

    return state


def _parse_verify_json(text: str) -> dict:
    """Parse JSON from LLM, with type normalization (v1 lesson)."""
    # Use shared JSON parser (Factor #4)
    data = parse_json(text)

    # Normalize types (v1 lesson: LLM output format never trustworthy)
    for key in ("issues", "fix_suggestions"):
        if key in data:
            normalized = []
            for item in data[key]:
                if isinstance(item, str):
                    normalized.append(item)
                elif isinstance(item, dict):
                    # Extract string from dict (v1 pitfall)
                    for k in ("issue", "suggestion", "text", "message", "description"):
                        if k in item and isinstance(item[k], str):
                            normalized.append(item[k])
                            break
                    else:
                        normalized.append(str(item))
                else:
                    normalized.append(str(item))
            data[key] = normalized

    return data
