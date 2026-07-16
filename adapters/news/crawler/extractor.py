"""Extractor — fetch HTML, discover selectors via LLM, extract with BeautifulSoup.

Flow:
  1. Check knowledge for cached selectors
  2. If cached → BeautifulSoup extract directly
  3. If not / stale → fetch HTML → LLM discover selectors → BeautifulSoup extract
  4. If selectors miss fields → LLM refine with one card's HTML (knowledge evolution)
  5. Cache selectors → next run skips LLM
"""

import json
import logging
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .knowledge import Knowledge
from .llm import discover_selectors

logger = logging.getLogger("news.extractor")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# Key fields that should be non-empty for quality extraction
KEY_FIELDS = ["title", "url", "cover_image", "published_date", "summary"]


def fetch_html(url: str, timeout: int = 30) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def fetch_stealth(url: str, timeout: int = 60) -> str | None:
    """Fetch URL through Scrapling's StealthyFetcher (bypasses Cloudflare, anti-bot).

    Returns HTML string or None if Scrapling is unavailable or fails.
    Impersonates Chrome 120 + solves Cloudflare Turnstile automatically.
    """
    try:
        from scrapling.fetchers import StealthyFetcher
    except ImportError:
        logger.warning("Scrapling not installed, cannot use stealth fetch")
        return None

    try:
        d = StealthyFetcher.fetch(
            url,
            headless=True,
            network_idle=True,
            solve_cloudflare=True,
            timeout=timeout,
        )
        raw = d.body
        encoding = d.encoding or "utf-8"
        html = raw.decode(encoding, errors="replace")
        logger.info(f"Stealth fetch OK: {len(html)} chars (status={d.status})")
        return html
    except Exception as e:
        logger.warning(f"Stealth fetch failed for {url}: {e}")
        return None


def _is_blocked(html: str) -> bool:
    """Detect anti-bot blocking CHALLENGE pages (not pages with Cloudflare scripts).

    A real page served through Cloudflare still has CF headers/scripts.
    We only flag it as blocked when the ENTIRE page is just a challenge interstitial.
    """
    lower = html.lower()
    # Cloudfront generic error page
    if "cloudfront" in lower and "<h1>403 error</h1>" in lower:
        return True
    if "request blocked" in lower and "cloudfront" in lower:
        return True
    # Cloudflare JS challenge interstitial (whole page is just the challenge)
    if "just a moment" in lower and "cf_chl" in lower:
        return True
    if "checking your browser" in lower and len(html) < 20000:
        return True
    return False


def _smart_fetch(url: str) -> str:
    """Fetch HTML, automatically escalating to stealth browser if blocked.

    Raises RuntimeError if all strategies fail.
    """
    try:
        html = fetch_html(url)
        if not _is_blocked(html):
            return html
        logger.info(f"requests blocked by anti-bot, trying stealth browser...")
    except Exception as e:
        logger.info(f"requests failed: {e}, trying stealth browser...")

    html = fetch_stealth(url)
    if html and not _is_blocked(html):
        return html

    raise RuntimeError(f"All fetch strategies failed for {url}")


def crawl_site(source: dict, knowledge: Knowledge) -> list[dict]:
    name = source["name"]
    url = source["url"]
    domain = urlparse(url).netloc

    logger.info(f"--- {name} ({domain}) ---")

    if knowledge.is_disabled(domain):
        logger.warning(f"{domain} disabled, skip")
        return []

    # Step 1: get selectors (cached or LLM)
    selectors = knowledge.get_selectors(domain)
    just_discovered = False

    if not selectors or not selectors.get("article"):
        try:
            html = _smart_fetch(url)
            result = discover_selectors(html, url)
            selectors = result.get("selectors", {})
            just_discovered = True
            if selectors and selectors.get("article"):
                knowledge.record_selectors(domain, selectors, 0)
            else:
                knowledge.record_failure(domain, "LLM returned no selectors")
                return []
        except Exception as e:
            logger.error(f"LLM discovery failed for {name}: {e}")
            knowledge.record_failure(domain, str(e)[:200])
            return []

    # Step 2: extract using selectors
    try:
        html = _smart_fetch(url)
        soup = BeautifulSoup(html, "html.parser")
        articles = _extract_articles(soup, selectors, url, name)

        if not articles:
            # If just discovered via LLM, try one refinement before giving up
            if just_discovered and selectors:
                logger.info(f"LLM selectors returned 0 articles, trying refinement...")
                refined = _refine_selectors(soup, selectors, html, url)
                if refined:
                    selectors = refined
                    knowledge.record_selectors(domain, refined, 0)
                    articles = _extract_articles(soup, refined, url, name)
                    if articles:
                        logger.info(f"Refined selectors recovered {len(articles)} articles")
                    else:
                        logger.warning(f"Refinement also returned 0 articles for {name}")
                        knowledge.record_extraction_result(domain, 0, success=False)
                        _invalidate_selectors(knowledge, domain)
                        return []
                else:
                    logger.warning(f"Selectors returned 0 articles for {name}")
                    knowledge.record_extraction_result(domain, 0, success=False)
                    _invalidate_selectors(knowledge, domain)
                    return []
            else:
                logger.warning(f"Selectors returned 0 articles for {name}")
                knowledge.record_extraction_result(domain, 0, success=False)
                _invalidate_selectors(knowledge, domain)
                return []

        # Step 3: check quality — if too many fields empty, refine selectors
        fill_rate = _field_fill_rate(articles)
        logger.info(f"Field fill rate: {fill_rate:.0%}")

        if fill_rate < 0.5 and selectors:
            logger.info(f"Low fill rate ({fill_rate:.0%}), refining selectors...")
            refined = _refine_selectors(soup, selectors, html, url)
            if refined:
                selectors = refined
                knowledge.record_selectors(domain, refined, 0)
                # Re-extract with refined selectors
                articles = _extract_articles(soup, refined, url, name)
                new_rate = _field_fill_rate(articles)
                logger.info(f"Refined fill rate: {new_rate:.0%}")

        knowledge.record_extraction_result(domain, len(articles), success=True)
        knowledge.reset_failures(domain)
        logger.info(f"Extracted {len(articles)} articles from {name}")
        return articles

    except Exception as e:
        logger.error(f"Extraction failed for {name}: {e}")
        knowledge.record_failure(domain, str(e)[:200])
        return []


def _invalidate_selectors(knowledge: Knowledge, domain: str):
    """Clear cached selectors so next run re-discovers."""
    site = knowledge.data.setdefault("sites", {}).get(domain, {})
    site["selectors"] = {}
    knowledge._save()


def _field_fill_rate(articles: list[dict]) -> float:
    """Fraction of non-empty values across key fields."""
    if not articles:
        return 0.0
    total = len(articles) * len(KEY_FIELDS)
    filled = sum(
        1 for a in articles for f in KEY_FIELDS
        if a.get(f) and a[f] != "N/A"
    )
    return filled / total


def _refine_selectors(soup: BeautifulSoup, current: dict, html: str, site_url: str) -> dict | None:
    """Send one article card's HTML to LLM to fix inaccurate selectors."""
    cards = soup.select(current["article"])
    if not cards:
        return None

    card_html = str(cards[0])
    if len(card_html) > 3000:
        card_html = card_html[:3000]

    from .llm import _get_client, _parse_json

    prompt = f"""The CSS selectors below are not extracting data correctly from this site.
Fix them by analyzing the HTML of one article card.

Current (broken) selectors:
{json.dumps(current, indent=2)}

Article card HTML:
```html
{card_html}
```

Return valid JSON with corrected selectors:
{{"selectors": {{"article": "...", "title": "...", "url": "...", "image": "...", "date": "...", "summary": "..."}}}}"""

    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1024,
        )
        text = resp.choices[0].message.content or ""
        result = _parse_json(text)
        new_selectors = result.get("selectors", {})
        if new_selectors and new_selectors.get("article"):
            logger.info(f"Refined selectors: {json.dumps(new_selectors)}")
            return new_selectors
    except Exception as e:
        logger.warning(f"Selector refinement failed: {e}")

    return None


def _extract_articles(
    soup: BeautifulSoup,
    selectors: dict,
    base_url: str,
    source_name: str,
) -> list[dict]:
    """Extract article data from page using CSS selectors."""
    cards = soup.select(selectors["article"])
    if not cards:
        logger.debug(f"Selector '{selectors['article']}' matched 0 elements")
        return []

    articles = []
    parsed_base = urlparse(base_url)

    for card in cards:
        title = _select_text(card, selectors.get("title", ""))
        url = _select_href(card, selectors.get("url", ""), base_url)
        image = _select_src(card, selectors.get("image", ""), base_url)
        date_str = _select_date(card, selectors.get("date", ""))
        summary = _select_text(card, selectors.get("summary", ""))

        if not title or not url:
            continue

        # Try URL-based date extraction as fallback
        if not date_str:
            date_str = _extract_date_from_url(url)

        # If summary is site-level boilerplate, discard it
        if summary and len(summary) < 20:
            summary = ""

        articles.append({
            "title": title.strip(),
            "url": url,
            "cover_image": image or "",
            "published_date": _parse_date_text(date_str),
            "summary": summary.strip() if summary else "",
            "source": source_name,
            "site_url": parsed_base.netloc,
        })

    return articles


# --- Selector helpers ---

def _select_text(el, selector: str) -> str:
    if not selector or selector.startswith("meta"):
        return ""
    found = el.select_one(selector)
    return found.get_text(strip=True) if found else ""


def _select_href(el, selector: str, base_url: str) -> str:
    if not selector:
        return ""
    found = el.select_one(selector)
    if not found:
        return ""
    href = found.get("href", "")
    return urljoin(base_url, href) if href else ""


def _select_src(el, selector: str, base_url: str) -> str:
    if not selector:
        return ""
    found = el.select_one(selector)
    if not found:
        return ""
    src = (
        found.get("src")
        or found.get("data-src")
        or found.get("data-lazy-src")
        or ""
    )
    if not src:
        srcset = found.get("srcset", "")
        if srcset:
            src = srcset.split(",")[0].strip().split(" ")[0]
    return urljoin(base_url, src) if src else ""


def _select_date(el, selector: str) -> str:
    if not selector or selector.startswith("meta"):
        return ""
    found = el.select_one(selector)
    if not found:
        return ""
    # Try datetime attr first, then text
    dt = found.get("datetime") or found.get("content") or ""
    if dt:
        return dt.strip()
    return found.get_text(strip=True) or ""


def _extract_date_from_url(url: str) -> str:
    """Extract date from URL path patterns like /headlines/2026/06/29/...

    Common patterns: /YYYY/MM/DD/, /YYYY-MM-DD/, /YYYY/MM/.
    Returns ISO date string or empty string.
    """
    m = re.search(r"/(\d{4})/(\d{1,2})/(\d{1,2})/", url)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
    m = re.search(r"/(\d{4})-(\d{2})-(\d{2})", url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return ""


def _parse_date_text(raw: str) -> str:
    """Extract and normalize date from mixed text like 'Spooky • December 24, 2024 • Tech'.

    Tries ISO 8601 first, then common text date patterns within longer strings.
    """
    if not raw:
        return ""
    raw = raw.strip()

    # Already ISO-ish
    if re.match(r"\d{4}-\d{2}-\d{2}T", raw):
        return raw[:19]

    # Extract date pattern from within text: "Month DD, YYYY"
    date_patterns = [
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}",
        r"\d{4}-\d{2}-\d{2}",
        r"\d{2}/\d{2}/\d{4}",
        r"\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}",
    ]
    for pat in date_patterns:
        m = re.search(pat, raw, re.IGNORECASE)
        if m:
            date_part = m.group(0)
            return _normalize_date(date_part)

    # Try direct parse
    return _normalize_date(raw)


def _normalize_date(raw: str) -> str:
    """Best-effort normalize to ISO 8601 date."""
    raw = raw.strip().rstrip(",")
    # Remove commas within date strings too (e.g. "December 24, 2024")
    raw = raw.replace(",", "")
    for fmt in [
        "%B %d %Y",
        "%b %d %Y",
        "%Y-%m-%d",
        "%d %B %Y",
        "%m/%d/%Y",
        "%d/%m/%Y",
    ]:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw
