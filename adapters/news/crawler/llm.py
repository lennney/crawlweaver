"""LLM — himodels.ai API thin wrapper for site selector discovery.

LLM analyzes HTML structure once, finds CSS selectors for article extraction.
Selectors get cached in knowledge.json so subsequent crawls skip the LLM.
BeautifulSoup does the actual extraction — LLM only does pattern recognition.
"""

import json
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger("news.llm")

DISCOVERY_PROMPT = """You are a web scraping assistant. Analyze this HTML from a news site homepage.

Find the CSS selectors that can extract news article data from this page. Look for repeated patterns (article cards, list items, post entries) that contain headlines, links, images, dates, and summaries.

Return valid JSON only (no markdown, no explanation):
{
  "selectors": {
    "article": "article.viral-card",
    "title": "h3.viral-title a",
    "url": "h3.viral-title a",
    "image": "img.attachment-large",
    "date": "time.published",
    "summary": "div.viral-excerpt"
  },
  "site_base_url": "https://www.example.com"
}

Rules:
- Each selector should be a valid CSS selector relative to the article container
- For the "date" selector, prefer elements with datetime attributes or time elements
- For the "image" selector, look for img tags (check src, data-src, and srcset attributes)
- If a field has no visible element, use "meta[property='og:description']" for summary or similar meta selectors
- The "article" selector should match each article card/container on the list page
- If the site uses og:meta tags (in <head>) for images/descriptions, note this — the extractor will handle og:meta differently
"""


def _get_client() -> OpenAI:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not set. Copy .env.example to .env and fill in your key.")
    return OpenAI(api_key=api_key, base_url=base_url)


def _compress_html(html: str, max_chars: int = 15000) -> str:
    """Strip noise, keep structural HTML. Samples from head + body."""
    # Remove script and style blocks
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
    html = re.sub(r"<noscript[^>]*>.*?</noscript>", "", html, flags=re.DOTALL)
    html = re.sub(r"<svg[^>]*>.*?</svg>", "", html, flags=re.DOTALL)
    # Remove excessive whitespace
    html = re.sub(r"\n\s*\n", "\n", html)
    html = re.sub(r"[ \t]+", " ", html)

    if len(html) <= max_chars:
        return html

    # Keep head (meta/og tags) + article-like body sections
    head_end = html.find("</head>")
    head = html[:head_end + 7] if head_end > 0 else html[:3000]
    body_start = html.find("<body")
    body = html[body_start:] if body_start > 0 else ""

    # Extract article-like chunks: look for repeating patterns
    article_chunks = re.findall(
        r'(<(?:article|div|li)[^>]*class="[^"]*(?:post|article|entry|card|item|story|news|viral)[^"]*"[^>]*>.*?</(?:article|div|li)>)',
        body, re.DOTALL | re.IGNORECASE
    )
    if article_chunks:
        # Keep first N article chunks
        chunk_text = "\n".join(article_chunks[:10])
        result = head + "\n<!-- ARTICLE CHUNKS -->\n" + chunk_text
        if len(result) > max_chars:
            result = result[:max_chars]
        return result

    # Fallback: take beginning + middle + end of body
    head_len = len(head)
    remaining = max_chars - head_len
    third = remaining // 3
    body_len = len(body)
    if body_len > remaining:
        body_sample = body[:third] + "\n<!-- ... -->\n" + body[body_len//2 - third//2:body_len//2 + third//2] + "\n<!-- ... -->\n" + body[-third:]
    else:
        body_sample = body
    return head + body_sample[:remaining]


def discover_selectors(html: str, site_url: str = "") -> dict:
    """Send HTML to LLM, get CSS selectors for article extraction.

    Returns: {selectors: {...}, site_base_url: str}
    The selectors are cached in knowledge.json for subsequent runs.
    Actual extraction is done by BeautifulSoup in extractor.py.
    """
    compressed = _compress_html(html)
    prompt = DISCOVERY_PROMPT
    if site_url:
        prompt += f"\n\nSITE URL: {site_url}"

    client = _get_client()

    for attempt in range(2):
        try:
            logger.info(f"LLM selector discovery attempt {attempt + 1} ({len(compressed)} chars HTML)")
            resp = client.chat.completions.create(
                model="deepseek-v4-flash",
                messages=[
                    {"role": "user", "content": f"{prompt}\n\nHTML:\n```html\n{compressed}\n```"}
                ],
                temperature=0.1,
                max_tokens=2048,
            )
            text = resp.choices[0].message.content or ""
            logger.debug(f"LLM raw ({len(text)} chars): {text[:400]}")

            result = _parse_json(text)
            selectors = result.get("selectors", {})

            if not selectors or not selectors.get("article"):
                raise ValueError("LLM returned no article selector")

            logger.info(f"LLM discovered selectors: {json.dumps(selectors)}")
            return result

        except Exception as e:
            logger.warning(f"LLM attempt {attempt + 1} failed: {e}")
            if attempt == 0:
                continue
            raise RuntimeError(f"LLM discovery failed after 2 attempts: {e}")

    return {"selectors": {}}


def _parse_json(text: str) -> dict:
    """Extract JSON from LLM response. Tries 3 strategies."""
    if not text or not text.strip():
        raise ValueError("Empty LLM response")

    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: code block
    m = re.search(r"```(?:json)?\s*\n?(.+?)\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: first { to last }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Cannot parse JSON from LLM response: {text[:300]}")
