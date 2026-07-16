"""Knowledge — cross-session site strategy evolution.

A simple JSON file that stores LLM-discovered selectors per domain.
The more we crawl a site, the less we need the LLM.

Evolution triggers:
- sample_count >= 3 + success_rate >= 0.8 → skip LLM, use cached selectors
- selectors return empty results → trigger LLM re-discovery (site redesign)
- 3 consecutive failures → mark site disabled, skip in future runs
"""

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("news.knowledge")

_lock = threading.Lock()

DEFAULT_PATH = Path(__file__).parent.parent / "data" / "knowledge.json"


class Knowledge:
    """Persistent site strategy store. Not a database — just one JSON file."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else DEFAULT_PATH
        self.data: dict = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"sites": {}, "failures": {}}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to load knowledge: {e}, starting fresh")
            return {"sites": {}, "failures": {}}

    def _save(self):
        with _lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(str(tmp), str(self.path))

    # --- Site strategy ---

    def get_selectors(self, domain: str) -> dict | None:
        """Get cached selectors for a domain if they're reliable enough.

        Returns selectors dict or None (need LLM discovery).
        """
        site = self.data.get("sites", {}).get(domain)
        if not site:
            return None
        selectors = site.get("selectors", {})
        if not selectors or not selectors.get("article"):
            return None
        # Use cached selectors if we have enough successful samples
        if site.get("sample_count", 0) >= 3 and site.get("success_rate", 0) >= 0.8:
            logger.info(f"Using cached selectors for {domain} (samples={site['sample_count']}, rate={site['success_rate']})")
            return selectors
        # For newer sites (< 3 samples), still use selectors but mark as provisional
        logger.info(f"Using provisional selectors for {domain} (samples={site.get('sample_count', 0)})")
        return selectors

    def record_selectors(self, domain: str, selectors: dict, article_count: int):
        """Store LLM-discovered selectors for a domain."""
        sites = self.data.setdefault("sites", {})
        if domain not in sites:
            sites[domain] = {"selectors": {}, "sample_count": 0, "total_articles": 0}
        site = sites[domain]
        site["selectors"] = selectors
        site["sample_count"] += 1
        site["total_articles"] += article_count
        site["success_rate"] = 1.0  # LLM said these work, start optimistic
        site["last_used"] = datetime.now().isoformat()
        site["last_llm_discovery"] = datetime.now().isoformat()
        self._save()
        logger.info(f"Recorded selectors for {domain}: {article_count} articles on discovery")

    def record_extraction_result(self, domain: str, article_count: int, success: bool):
        """Update success rate after a cached-selector extraction."""
        site = self.data.get("sites", {}).get(domain)
        if not site:
            return
        site["sample_count"] += 1
        site["total_articles"] += article_count
        site["last_used"] = datetime.now().isoformat()

        # Moving average success rate
        old_rate = site.get("success_rate", 1.0)
        weight = 0.3  # recent results weighted more
        new_rate = old_rate * (1 - weight) + (1.0 if success else 0.0) * weight
        site["success_rate"] = round(new_rate, 2)

        if not success:
            logger.warning(f"Selectors failed for {domain}, marking for re-discovery")
            # Force LLM re-discovery on next crawl
            site["selectors"] = {}

        self._save()

    # --- Failure tracking ---

    def is_disabled(self, domain: str) -> bool:
        """Check if a site has been disabled due to repeated failures."""
        return self.data.get("failures", {}).get(domain, {}).get("disabled", False)

    def should_skip(self, domain: str) -> bool:
        """Check if domain should be skipped (disabled or 3+ failures)."""
        failures = self.data.get("failures", {}).get(domain, {})
        return failures.get("disabled", False) or failures.get("count", 0) >= 3

    def record_failure(self, domain: str, reason: str):
        """Record a failure for a domain. Auto-disable after 3 consecutive failures."""
        failures = self.data.setdefault("failures", {})
        if domain not in failures:
            failures[domain] = {"count": 0, "reasons": [], "disabled": False}
        f = failures[domain]
        f["count"] += 1
        f["reasons"].append(reason)
        if f["count"] >= 3:
            f["disabled"] = True
            logger.warning(f"Domain {domain} disabled after {f['count']} failures: {reason}")
        self._save()

    def reset_failures(self, domain: str):
        """Reset failure count (e.g. after a successful crawl)."""
        if domain in self.data.get("failures", {}):
            del self.data["failures"][domain]
            self._save()

    # --- Stats ---

    def stats(self) -> dict:
        sites = self.data.get("sites", {})
        return {
            "total_sites": len(sites),
            "cached_sites": sum(1 for s in sites.values() if s.get("selectors", {}).get("article")),
            "total_articles": sum(s.get("total_articles", 0) for s in sites.values()),
            "disabled_sites": sum(1 for f in self.data.get("failures", {}).values() if f.get("disabled")),
        }
