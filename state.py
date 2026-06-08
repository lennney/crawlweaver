"""CrawlState — unified execution + business state (Factor #5).

Single Pydantic model that IS the memory. No separate memory layer.
Events list IS the short-term history. State fields ARE the working memory.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar, Optional

from pydantic import BaseModel, Field

# Maximum events to retain in memory (prevents unbounded growth in long pipelines)
MAX_EVENTS = 20


# --- Enums ---

class Source(str, Enum):
    YOUTUBE = "youtube"
    WEB = "web"
    REDDIT = "reddit"
    TWITTER = "twitter"
    WECHAT = "wechat"
    ZHIHU = "zhihu"


class Step(str, Enum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    REWRITTEN = "rewritten"
    SEO_DONE = "seo_done"
    RENDERED = "rendered"
    VERIFIED = "verified"
    REVIEW = "review"
    PASSED = "passed"
    FAILED = "failed"


# --- Sub-models ---

class SeoMetadata(BaseModel):
    title_tag: str = ""
    meta_description: str = ""
    url_slug: str = ""
    h1: str = ""


class VerifyResult(BaseModel):
    score: int = 0
    passed: bool = False
    dimensions: dict[str, Any] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    fix_suggestions: list[str] = Field(default_factory=list)


class CrawlEvent(BaseModel):
    """Immutable event — appended after each tool execution."""
    step: str
    tool: str
    success: bool
    message: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    data: dict[str, Any] = Field(default_factory=dict)


# --- Main State ---

class CrawlState(BaseModel):
    """The single source of truth for one crawl job.
    
    Execution state (step, events, attempts) and business state
    (raw_text, article_md, seo) live together — Factor #5.
    """

    # Class-level lock (shared across instances, avoids pickle issues)
    _event_lock: ClassVar[threading.Lock] = threading.Lock()

    # Identity
    url: str = ""
    source: Source = Source.YOUTUBE
    keyword: str = ""
    content_type: str = "Beginner Guide"
    target_words: int = 1200

    # Raw content (populated by extract)
    title: str = ""
    raw_text: str = ""
    source_metadata: dict[str, Any] = Field(default_factory=dict)

    # Article (populated by rewrite)
    article_md: str = ""

    # SEO (populated by seo tool)
    seo: SeoMetadata = Field(default_factory=SeoMetadata)

    # HTML (populated by render)
    html_path: str = ""

    # Verify (populated by verify tool)
    verify: Optional[VerifyResult] = None

    # Failure report (Factor #7: set on failure)
    failure_report: Optional[dict] = None

    # Sprint 4: Knowledge-guided extraction strategy
    preferred_extractor: str = ""  # Set by reducer from site_patterns

    # Execution state (unified with business state)
    step: Step = Step.PENDING
    events: list[CrawlEvent] = Field(default_factory=list)
    error: str = ""
    attempts: int = 0

    def append_event(self, tool: str, success: bool, message: str = "", **data):
        event = CrawlEvent(
            step=self.step.value,
            tool=tool,
            success=success,
            message=message,
            data=data if data else {},
        )
        # Thread-safe: lock prevents lost updates from concurrent append + slice
        with CrawlState._event_lock:
            self.events.append(event)
            if len(self.events) > MAX_EVENTS:
                self.events = self.events[-MAX_EVENTS:]

    def last_verify_errors(self) -> list[str]:
        """Get all unique errors from verify events — for context injection.

        Accumulates errors across all fix attempts (Manus pattern: never
        compress error traces, helps avoid repeating mistakes).
        Returns newest errors first, deduplicated.
        """
        seen: set[str] = set()
        all_errors: list[str] = []
        for evt in reversed(self.events):
            if evt.tool == "verify" and not evt.success:
                for err in evt.data.get("issues", []):
                    if err not in seen:
                        seen.add(err)
                        all_errors.append(err)
        return all_errors

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

    @classmethod
    def from_json(cls, text: str) -> "CrawlState":
        return cls.model_validate_json(text)

    def save(self, path: str | Path):
        Path(path).write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "CrawlState":
        return cls.from_json(Path(path).read_text(encoding="utf-8"))


# --- Factory ---

def make_state(url: str, source: str = "youtube", keyword: str = "", **kw) -> CrawlState:
    """Create a new CrawlState from minimal inputs."""
    return CrawlState(
        url=url,
        source=Source(source),
        keyword=keyword,
        **kw,
    )
