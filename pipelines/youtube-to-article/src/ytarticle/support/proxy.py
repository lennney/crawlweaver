"""Proxy management for yt-dlp."""
from __future__ import annotations
import os
from typing import Optional


class ProxyManager:
    """Manage proxy configuration for yt-dlp."""

    def __init__(self, http: Optional[str] = None, https: Optional[str] = None):
        self.http = http or os.environ.get("HTTP_PROXY", "")
        self.https = https or os.environ.get("HTTPS_PROXY", http or os.environ.get("HTTP_PROXY", ""))

    @property
    def enabled(self) -> bool:
        return bool(self.http) or bool(self.https)

    def yt_dlp_args(self) -> list[str]:
        if self.http:
            return ["--proxy", self.http]
        return []
