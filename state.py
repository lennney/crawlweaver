"""CrawlState — unified execution + business state (Factor #5).

Single Pydantic model that IS the memory. No separate memory layer.
Events list IS the short-term history. State fields ARE the working memory.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


# --- Enums ---

class Source(str, Enum):
    YOUTUBE = "youtube"
    WEB = "web"
    REDDIT = "reddit"


class Step(str, Enum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    REWRITTEN = "rewritten"
    SEO_DONE = "seo_done"
    RENDERED = "rendered"
    VERIFIED = "verified"
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

    # Execution state (unified with business state)
    step: Step = Step.PENDING
    events: list[CrawlEvent] = Field(default_factory=list)
    error: str = ""
    attempts: int = 0

    def append_event(self, tool: str, success: bool, message: str = "", **data):
        self.events.append(CrawlEvent(
            step=self.step.value,
            tool=tool,
            success=success,
            message=message,
            data=data if data else {},
        ))

    def last_verify_errors(self) -> list[str]:
        """Get errors from the most recent verify event — for context injection."""
        for evt in reversed(self.events):
            if evt.tool == "verify" and not evt.success:
                return evt.data.get("issues", [])
        return []

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
