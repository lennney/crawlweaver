"""知乎 (Zhihu) article/answer extractor.

Supports two URL patterns:
- 专栏文章: zhihu.com/p/{id} or zhuanlan.zhihu.com/p/{id}
- 问答回答: zhihu.com/question/{q_id}/answer/{a_id}

Strategy:
1. Try Zhihu API endpoint (fast, structured)
2. Fall back to web scraping

Sprint 5: Multi-source extension.
"""

import json
import logging
import re

from state import CrawlState

logger = logging.getLogger("crawler.extract.zhihu")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.zhihu.com/",
}


def extract_zhihu(state: CrawlState) -> None:
    """Extract content from a Zhihu article or answer URL.

    Dispatches based on URL pattern:
    - zhuanlan.zhihu.com/p/xxx or zhihu.com/p/xxx → article
    - zhihu.com/question/xxx/answer/xxx → answer
    """
    url = state.url

    if _is_answer_url(url):
        _extract_answer(state)
    elif _is_article_url(url):
        _extract_article(state)
    else:
        _extract_web_fallback(state)


def _is_answer_url(url: str) -> bool:
    return bool(re.search(r"zhihu\.com/question/\d+/answer/\d+", url))


def _is_article_url(url: str) -> bool:
    return bool(re.search(r"(zhuanlan\.)?zhihu\.com/p/\d+", url))


def _extract_article(state: CrawlState) -> None:
    """Extract Zhihu column article via API or scraping."""
    import requests
    from bs4 import BeautifulSoup

    url = state.url
    article_id = re.search(r"/p/(\d+)", url)
    if not article_id:
        raise ValueError(f"Cannot parse article ID from: {url}")
    aid = article_id.group(1)

    # Strategy 1: API
    try:
        api_url = f"https://zhuanlan.zhihu.com/api/articles/{aid}"
        resp = requests.get(api_url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        state.title = data.get("title", "")
        content_html = data.get("content", "")
        if content_html:
            soup = BeautifulSoup(content_html, "html.parser")
            for tag in soup.find_all(["script", "style"]):
                tag.decompose()
            state.raw_text = soup.get_text(separator="\n", strip=True)
            state.source_metadata = {
                "method": "api",
                "article_id": aid,
                "author": data.get("author", {}).get("name", ""),
                "voteup_count": data.get("voteup_count", 0),
            }
            return
    except Exception as e:
        logger.warning(f"Zhihu article API failed: {e}, trying scraping")

    _extract_web_fallback(state, article_id=aid)


def _extract_answer(state: CrawlState) -> None:
    """Extract Zhihu answer via API or scraping."""
    import requests
    from bs4 import BeautifulSoup

    url = state.url
    m = re.search(r"question/(\d+)/answer/(\d+)", url)
    if not m:
        raise ValueError(f"Cannot parse question/answer IDs from: {url}")

    question_id, answer_id = m.group(1), m.group(2)

    # Strategy 1: Answer API
    try:
        api_url = f"https://www.zhihu.com/api/v4/answers/{answer_id}"
        params = {"include": "content,excerpt,comment_count,voteup_count"}
        resp = requests.get(api_url, headers=_HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        state.title = data.get("question", {}).get("title", "")
        content_html = data.get("content", "")
        if content_html:
            soup = BeautifulSoup(content_html, "html.parser")
            for tag in soup.find_all(["script", "style"]):
                tag.decompose()
            state.raw_text = soup.get_text(separator="\n", strip=True)
            state.source_metadata = {
                "method": "api",
                "question_id": question_id,
                "answer_id": answer_id,
                "author": data.get("author", {}).get("name", ""),
                "voteup_count": data.get("voteup_count", 0),
            }
            return
    except Exception as e:
        logger.warning(f"Zhihu answer API failed: {e}, trying scraping")

    _extract_web_fallback(state)


def _extract_web_fallback(state: CrawlState, article_id: str = "") -> None:
    """Scrape Zhihu content from the HTML page."""
    import requests
    from bs4 import BeautifulSoup

    resp = requests.get(state.url, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    # Try og:title and og:description
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        state.title = str(og_title["content"])

    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        state.raw_text = str(og_desc["content"])
        state.source_metadata = {"method": "og_meta"}
        return

    # Try JSON-LD data
    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                if "articleBody" in data:
                    state.raw_text = data["articleBody"]
                    state.source_metadata = {"method": "json-ld"}
                    return
        except (json.JSONDecodeError, TypeError):
            continue

    # Last resort: extract visible text
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    body = soup.get_text(separator="\n", strip=True)
    if len(body) > 200:
        state.raw_text = body[:10000]
        state.source_metadata = {"method": "scraping_fallback"}
    else:
        raise RuntimeError(f"Could not extract meaningful content from Zhihu URL: {state.url}")
