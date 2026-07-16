"""Unified data contract — single schema all components share."""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class Source(str, Enum):
    YOUTUBE = "youtube"
    CUSTOM = "custom"


class ImageInfo(BaseModel):
    path: str = ""
    alt: str = ""
    source_url: str = ""
    step: int = 0


class ArtifactPaths(BaseModel):
    raw_text: str = ""
    article_md: str = ""
    html_path: str = ""
    images_dir: str = ""
    timed_transcript: str = ""
    cover_img: str = ""


class SeoMetadata(BaseModel):
    title_tag: str = ""
    meta_description: str = ""
    url_slug: str = ""
    h1: str = ""


class ContentItem(BaseModel):
    """Unified data contract. All components read/write this."""

    # --- Source ---
    source: Source = Source.YOUTUBE
    source_id: str = ""
    source_url: str = ""
    source_metadata: dict[str, Any] = Field(default_factory=dict)

    # --- Raw ---
    title: str = ""
    raw_text: str = ""
    images: list[ImageInfo] = Field(default_factory=list)

    # --- Classification ---
    category: str = ""
    keyword: str = ""
    tags: list[str] = Field(default_factory=list)
    target_words: int = 1500
    author: str = ""

    # --- Article ---
    article_md: str = ""
    difficulty: str = ""
    estimated_time: str = ""
    estimated_cost: str = ""
    materials: list[str] = Field(default_factory=list)

    # --- SEO ---
    seo: SeoMetadata = Field(default_factory=SeoMetadata)

    # --- Artifacts ---
    artifacts: ArtifactPaths = Field(default_factory=ArtifactPaths)

    # --- Pipeline state ---
    status: str = "pending"
    error: str = ""
    started_at: str = ""
    completed_at: str = ""

    def mark_running(self):
        self.status = "running"
        if not self.started_at:
            self.started_at = datetime.now().isoformat()

    def mark_done(self):
        self.status = "done"
        self.completed_at = datetime.now().isoformat()

    def mark_failed(self, error: str):
        self.status = "failed"
        self.error = error
        self.completed_at = datetime.now().isoformat()

    def task_id(self) -> str:
        return f"{self.source.value}_{self.source_id}"


def make_item(source: str, source_id: str, **kw) -> ContentItem:
    return ContentItem(source=Source(source), source_id=source_id, **kw)
