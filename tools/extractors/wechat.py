"""WeChat Official Account (微信公众号) article extractor.

Strategy:
1. Fetch article page with requests (WeChat articles don't need JS)
2. Extract from #js_content div (the standard article container)
3. Parse title from activity-name header

Sprint 5: Multi-source extension.
"""

import logging

from state import CrawlState

logger = logging.getLogger("crawler.extract.wechat")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
}


def extract_wechat(state: CrawlState) -> None:
    """Extract article content from a WeChat Official Account URL.

    WeChat articles (mp.weixin.qq.com) render server-side,
    so simple requests + BeautifulSoup works.
    """
    import requests
    from bs4 import BeautifulSoup

    url = state.url

    if "mp.weixin.qq.com" not in url:
        raise ValueError(f"Not a WeChat article URL: {url}")

    resp = requests.get(url, headers=_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"

    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract title
    title_el = soup.find(id="activity-name")
    if title_el:
        state.title = str(title_el.get_text(strip=True))
    else:
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            state.title = str(og_title["content"])
        else:
            state.title = ""

    # Extract article body
    content_el = soup.find(id="js_content")
    if content_el:
        # Remove images (keep text)
        for img in content_el.find_all("img"):
            alt = img.get("alt", "")
            if alt:
                img.replace_with(f"[图片: {alt}]")
            else:
                img.decompose()

        # Remove style/script tags
        for tag in content_el.find_all(["script", "style"]):
            tag.decompose()

        text = content_el.get_text(separator="\n", strip=True)
        state.raw_text = text
    else:
        # Fallback: try og:description
        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            state.raw_text = str(og_desc["content"])
        else:
            raise RuntimeError("Could not find article content in WeChat page")

    # Extract author
    author_el = soup.find(id="js_name") or soup.find("a", id="js_name")
    if author_el:
        state.source_metadata = {"author": author_el.get_text(strip=True)}

    # Extract publish time
    pub_time = soup.find(id="publish_time")
    if pub_time:
        state.source_metadata = state.source_metadata or {}
        state.source_metadata["publish_time"] = pub_time.get_text(strip=True)

    logger.info(f"WeChat article extracted: {len(state.raw_text)} chars, title={state.title!r}")
