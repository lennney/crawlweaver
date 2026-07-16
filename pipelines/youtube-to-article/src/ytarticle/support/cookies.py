"""Cookie management for yt-dlp."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional


class CookieManager:
    """Manage YouTube cookies for yt-dlp authentication."""

    def __init__(self, cookie_path: Optional[str] = None):
        self._path: Optional[Path] = None
        if cookie_path:
            self._path = Path(cookie_path)
        elif "COOKIES_PATH" in os.environ:
            self._path = Path(os.environ["COOKIES_PATH"])

    @property
    def path(self) -> Optional[str]:
        return str(self._path) if self._path else None

    @property
    def exists(self) -> bool:
        return self._path is not None and self._path.exists()

    @property
    def is_valid(self) -> bool:
        if not self.exists:
            return False
        try:
            content = self._path.read_text(encoding="utf-8")
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    parts = line.split("\t")
                    if len(parts) >= 6:
                        return True
            return False
        except OSError:
            return False

    def yt_dlp_args(self) -> list[str]:
        if self.exists:
            return ["--cookies", str(self._path)]
        return []
