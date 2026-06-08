"""Twitter/X tweet extractor.

Strategy:
1. Try Twitter oembed API (no auth, works for public tweets)
2. Fall back to web scraping with mobile User-Agent

Sprint 5: Multi-source extension.
"""

import logging
import re

from state import CrawlState

logger = logging.getLogger("crawler.extract.twitter")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                  "Version/17.0 Mobile/15E148 Safari/604.1",
}


def extract_twitter(state: CrawlState) -> None:
    """Extract tweet content from a Twitter/X URL.

    Tries oembed API first (lightweight, no scraping).
    Falls back to direct HTML scraping if oembed fails.
    """
    import requests
    from bs4 import BeautifulSoup

    url = state.url
    tweet_id = _extract_tweet_id(url)
    if not tweet_id:
        raise ValueError(f"Cannot parse tweet ID from URL: {url}")

    # Strategy 1: oembed API
    try:
        resp = requests.get(
            f"https://publish.twitter.com/oembed?url={url}&omit_script=true",
            headers=_HEADERS, timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        html = data.get("html", "")
        author_name = data.get("author_name", "")
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator="\n", strip=True)

        state.raw_text = text
        state.title = f"Tweet by @{author_name}" if author_name else f"Tweet {tweet_id}"
        state.source_metadata = {"method": "oembed", "tweet_id": tweet_id}
        return
    except Exception as e:
        logger.warning(f"oembed failed: {e}, trying direct scraping")

    # Strategy 2: Direct scraping via mobile UA
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            state.raw_text = str(og_desc["content"])
            og_title = soup.find("meta", property="og:title")
            state.title = str(og_title["content"]) if og_title and og_title.get("content") else f"Tweet {tweet_id}"
            state.source_metadata = {"method": "scraping", "tweet_id": tweet_id}
            return

        raise RuntimeError("Could not extract tweet content from page")
    except Exception as e:
        raise RuntimeError(f"All Twitter extraction methods failed for {url}: {e}")


def _extract_tweet_id(url: str) -> str | None:
    """Extract tweet ID from twitter.com or x.com URL."""
    patterns = [
        r"(?:twitter\.com|x\.com)/\w+/status/(\d+)",
        r"(?:twitter\.com|x\.com)/\w+/statuses/(\d+)",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None
