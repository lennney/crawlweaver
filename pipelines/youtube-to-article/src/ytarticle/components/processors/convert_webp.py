"""Convert step images from JPG to WebP using ffmpeg."""
from __future__ import annotations
import logging
import subprocess
from pathlib import Path
from typing import Any

from ytarticle.core.base import BaseComponent
from ytarticle.core.schema import ContentItem

logger = logging.getLogger("ytarticle.convert_webp")


class ConvertWebP(BaseComponent):
    name = "convert_webp"
    version = "1.0.0"
    required_fields = ["images"]
    output_fields = ["images"]

    def run(self, item: ContentItem, config: dict[str, Any]) -> ContentItem:
        images = item.images
        if not images:
            return item

        quality = config.get("quality", 85)
        converted = 0

        for img in images:
            path_str = img.path
            if not path_str:
                continue
            p = Path(path_str)
            if p.suffix.lower() not in (".jpg", ".jpeg") or not p.exists():
                continue

            webp_path = p.with_suffix(".webp")
            try:
                result = subprocess.run(
                    ["cwebp", "-q", str(quality), str(p), "-o", str(webp_path)],
                    capture_output=True, text=True, timeout=30)
            except (subprocess.TimeoutExpired, OSError) as e:
                logger.warning(f"[convert_webp] Failed {p.name}: {e}")
                continue

            if result.returncode == 0 and webp_path.exists():
                p.unlink(missing_ok=True)
                img.path = str(webp_path)
                converted += 1
                logger.debug(f"[convert_webp] {p.name} → {webp_path.name}")
            else:
                webp_path.unlink(missing_ok=True)

        if converted:
            logger.info(f"[convert_webp] Converted {converted}/{len(images)} images to WebP")
        return item


def create():
    return ConvertWebP()