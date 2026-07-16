"""News Aggregator — multi-source crawler entry point.

Usage:
    python crawler.py              # crawl all sources, save to data/news.json
    python crawler.py --stats      # show knowledge stats
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from crawler.extractor import crawl_site
from crawler.knowledge import Knowledge
from crawler.sources import SOURCES

DATA_DIR = Path(__file__).parent / "data"
NEWS_FILE = DATA_DIR / "news.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("crawler")


def run(sources: list[dict] | None = None) -> None:
    """Crawl all sources, merge results into news.json."""
    if sources is None:
        sources = SOURCES

    knowledge = Knowledge()

    all_articles = _load_existing()

    for src in sources:
        articles = crawl_site(src, knowledge)
        if not articles:
            logger.info(f"No articles from {src['name']}")
            continue

        # Add ID and timestamps
        for a in articles:
            a.setdefault("id", _make_id(a.get("url", "")))
            a.setdefault("crawled_at", datetime.now().isoformat())

        # Merge: deduplicate by URL
        existing_urls = {a["url"] for a in all_articles}
        new_count = 0
        for a in articles:
            if a["url"] not in existing_urls:
                all_articles.append(a)
                existing_urls.add(a["url"])
                new_count += 1
        logger.info(f"Added {new_count} new articles from {src['name']} (total {len(articles)} fetched)")

    _save_articles(all_articles)

    # Summary
    kb_stats = knowledge.stats()
    logger.info(f"--- Summary ---")
    logger.info(f"Total articles in store: {len(all_articles)}")
    logger.info(f"Knowledge: {kb_stats['cached_sites']} sites cached, {kb_stats['total_sites']} known, {kb_stats['disabled_sites']} disabled")


def _load_existing() -> list[dict]:
    if NEWS_FILE.exists():
        try:
            return json.loads(NEWS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_articles(articles: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    NEWS_FILE.write_text(json.dumps(articles, indent=2, ensure_ascii=False), encoding="utf-8")


def _make_id(url: str) -> str:
    import hashlib
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def show_stats() -> None:
    knowledge = Knowledge()
    stats = knowledge.stats()
    print(json.dumps(stats, indent=2))


def main():
    parser = argparse.ArgumentParser(description="News Aggregator Crawler")
    parser.add_argument("--stats", action="store_true", help="Show knowledge stats")
    args = parser.parse_args()

    if args.stats:
        show_stats()
    else:
        run()


if __name__ == "__main__":
    main()
