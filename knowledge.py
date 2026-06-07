"""Knowledge — cross-session persistence (Factor #13: Pre-fetch).

NOT a vector database. NOT a memory system.
A simple JSON file that stores: URL history, site patterns, prompt stats.
Loaded deterministically before reducer runs — not searched by LLM.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("crawler.knowledge")


class SitePattern(BaseModel):
    extractor: str = ""
    best_prompt: str = ""
    avg_quality: float = 0.0
    sample_count: int = 0
    total_quality: float = 0.0


class KeywordCoverage(BaseModel):
    keyword: str = ""
    covered: bool = False
    article_url: str = ""
    score: int = 0
    covered_at: str = ""


class FailureRecord(BaseModel):
    url: str
    error: str
    count: int = 1
    last_seen: str = Field(default_factory=lambda: datetime.now().isoformat())


class PromptStats(BaseModel):
    avg_score: float = 0.0
    count: int = 0
    total_score: float = 0.0

    def record(self, score: int):
        self.count += 1
        self.total_score += score
        self.avg_score = self.total_score / self.count


class Knowledge(BaseModel):
    """Cross-session knowledge — pre-loaded into reducer context."""

    crawled_urls: set[str] = Field(default_factory=set)
    site_patterns: dict[str, SitePattern] = Field(default_factory=dict)
    failure_log: list[FailureRecord] = Field(default_factory=list)
    prompt_stats: dict[str, PromptStats] = Field(default_factory=dict)
    keyword_coverage: dict[str, KeywordCoverage] = Field(default_factory=dict)

    def was_crawled(self, url: str) -> bool:
        return url in self.crawled_urls

    def record_crawl(self, url: str):
        self.crawled_urls.add(url)

    def record_failure(self, url: str, error: str):
        for rec in self.failure_log:
            if rec.url == url and rec.error == error:
                rec.count += 1
                rec.last_seen = datetime.now().isoformat()
                return
        self.failure_log.append(FailureRecord(url=url, error=error))

    def record_quality(self, prompt_path: str, score: int):
        if prompt_path not in self.prompt_stats:
            self.prompt_stats[prompt_path] = PromptStats()
        self.prompt_stats[prompt_path].record(score)

    def record_site_pattern(self, domain: str, extractor: str, prompt: str, quality: int):
        """Record or update site pattern with moving average quality."""
        if domain in self.site_patterns:
            sp = self.site_patterns[domain]
            sp.sample_count += 1
            sp.total_quality += quality
            sp.avg_quality = sp.total_quality / sp.sample_count
        else:
            self.site_patterns[domain] = SitePattern(
                extractor=extractor,
                best_prompt=prompt,
                avg_quality=float(quality),
                sample_count=1,
                total_quality=float(quality),
            )

    def best_prompt_for(self, source_type: str, candidates: list[str]) -> str:
        """Pick the prompt with highest avg score. Fallback to first candidate."""
        best = candidates[0]
        best_avg = 0.0
        for p in candidates:
            stats = self.prompt_stats.get(p)
            if stats and stats.count >= 3 and stats.avg_score > best_avg:
                best_avg = stats.avg_score
                best = p
        return best

    def failure_count(self, url: str) -> int:
        return sum(r.count for r in self.failure_log if r.url == url)

    def record_coverage(self, keyword: str, article_url: str, score: int):
        """Record that a keyword has been covered."""
        self.keyword_coverage[keyword] = KeywordCoverage(
            keyword=keyword,
            covered=True,
            article_url=article_url,
            score=score,
            covered_at=datetime.now().isoformat(),
        )

    def add_target_keyword(self, keyword: str):
        """Add a target keyword (not yet covered)."""
        if keyword not in self.keyword_coverage:
            self.keyword_coverage[keyword] = KeywordCoverage(
                keyword=keyword, covered=False,
            )

    def coverage_summary(self) -> dict:
        covered = sum(1 for c in self.keyword_coverage.values() if c.covered)
        targeted = sum(1 for c in self.keyword_coverage.values() if not c.covered)
        return {"covered": covered, "targeted": targeted, "total_keywords": len(self.keyword_coverage)}


def load_knowledge(path: str | Path) -> Knowledge:
    p = Path(path)
    if not p.exists():
        logger.info(f"No knowledge file at {path}, starting fresh")
        return Knowledge()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        # set is not JSON-serializable, convert list back
        if "crawled_urls" in data and isinstance(data["crawled_urls"], list):
            data["crawled_urls"] = set(data["crawled_urls"])
        return Knowledge.model_validate(data)
    except Exception as e:
        logger.warning(f"Failed to load knowledge: {e}, starting fresh")
        return Knowledge()


def save_knowledge(knowledge: Knowledge, path: str | Path):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = knowledge.model_dump()
    # set → list for JSON serialization
    data["crawled_urls"] = list(data["crawled_urls"])
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Knowledge saved to {path}")
