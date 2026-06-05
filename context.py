"""Context Engineering — decide what the LLM sees (Factor #3 + #13).

Pre-fetch pattern: code loads relevant data deterministically.
LLM never needs to "search memory" or "recall" — it's already in context.
"""

from state import CrawlState
from knowledge import Knowledge


def build_rewrite_context(state: CrawlState, knowledge: Knowledge) -> str:
    """Build the user prompt for the rewrite tool."""
    parts = [
        f"## Source Content\n{state.raw_text[:3000]}",
        f"\n## Keyword: {state.keyword}",
        f"## Article Type: {state.content_type}",
        f"## Target Words: {state.target_words}",
    ]

    # If we've failed verification before, inject the errors (Factor #9)
    errors = state.last_verify_errors()
    if errors:
        parts.append("\n## Previous Verification Errors (fix these)")
        for err in errors:
            parts.append(f"- {err}")

    return "\n".join(parts)


def build_seo_context(state: CrawlState) -> str:
    """Build the user prompt for the SEO tool."""
    return (
        f"## Article Title\n{state.title}\n\n"
        f"## Article (first 2000 chars)\n{state.article_md[:2000]}\n\n"
        f"## Keyword: {state.keyword}"
    )


def build_verify_context(state: CrawlState) -> str:
    """Build the user prompt for the verify tool."""
    return (
        f"## Original Source (first 3000 chars)\n{state.raw_text[:3000]}\n\n"
        f"## Generated Article (first 4000 chars)\n{state.article_md[:4000]}\n\n"
        f"## Keyword: {state.keyword}"
    )
