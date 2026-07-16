"""YouTube subtitle extraction via yt-dlp with deno JS runtime for n-challenge."""
from __future__ import annotations
import json
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from ytarticle.core.base import BaseComponent, ComponentError
from ytarticle.core.schema import ContentItem
from ytarticle.support.cookies import CookieManager
from ytarticle.support.proxy import ProxyManager

logger = logging.getLogger("ytarticle.youtube_extract")


class YouTubeExtract(BaseComponent):
    name = "youtube_extract"
    version = "2.0.0"
    required_fields = ["source_id"]
    output_fields = ["title", "raw_text", "source_metadata"]

    @staticmethod
    def _find_deno() -> str:
        """Find deno binary for JS challenge solving."""
        import shutil
        import os
        deno = os.environ.get("DENO_PATH", "")
        if deno and Path(deno).exists():
            return deno
        deno = shutil.which("deno")
        if deno:
            return deno
        fallback = os.path.expanduser("~/.deno/bin/deno")
        if Path(fallback).exists():
            return fallback
        return ""

    @staticmethod
    def _js_flags() -> list[str]:
        """Build JS runtime flags for n-challenge solving."""
        deno = YouTubeExtract._find_deno()
        if deno:
            return ["--js-runtimes", f"deno:{deno}",
                    "--remote-components", "ejs:github"]
        return []

    def _download_metadata(self, video_id: str, cookies: CookieManager,
                           proxy: ProxyManager) -> dict:
        cmd = [sys.executable, "-m", "yt_dlp",
               "--dump-json", "--skip-download",
               "--no-warnings",
               *cookies.yt_dlp_args(),
               *proxy.yt_dlp_args(),
               *self._js_flags(),
               "--impersonate", "chrome",
               f"https://www.youtube.com/watch?v={video_id}"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise ComponentError(f"yt-dlp metadata failed: {result.stderr[-300:]}")
        return json.loads(result.stdout)

    def _download_transcript(self, video_id: str, output_dir: Path,
                             cookies: CookieManager, proxy: ProxyManager) -> tuple[str, str]:
        text_path = output_dir / f"{video_id}.txt"
        json_path = output_dir / f"{video_id}_timed.json"

        # Strategy 1: json3 format (preferred — cleaner, timed)
        strategies = [
            (["--write-auto-sub", "--sub-lang", "en", "--sub-format", "json3"], "json3"),
            (["--write-subs", "--write-auto-subs", "--sub-langs", "en,-live_chat",
              "--convert-subs", "srt", "--sub-format", "vtt/txt"], "vtt"),
        ]

        for sub_args, fmt_name in strategies:
            for f in output_dir.glob(f"{video_id}*"):
                try:
                    f.unlink()
                except OSError:
                    pass

            cmd = [sys.executable, "-m", "yt_dlp",
                   "--skip-download",
                   *sub_args,
                   "--no-warnings",
                   *cookies.yt_dlp_args(),
                   *proxy.yt_dlp_args(),
                   *self._js_flags(),
                   "--impersonate", "chrome",
                   "-o", str(output_dir / f"{video_id}.%(ext)s"),
                   f"https://www.youtube.com/watch?v={video_id}"]

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            except (subprocess.TimeoutExpired, OSError) as e:
                logger.warning(f"Transcript download ({fmt_name}) error: {e}")
                continue
            if result.returncode != 0:
                logger.warning(f"Transcript download ({fmt_name}) failed: {result.stderr[-200:]}")
                continue

            if fmt_name == "json3":
                # Parse json3 format
                json3_file = output_dir / f"{video_id}.en.json3"
                if not json3_file.exists():
                    found = list(output_dir.glob(f"{video_id}*.json3"))
                    json3_file = found[0] if found else None
                if json3_file and json3_file.stat().st_size > 0:
                    return self._parse_json3(json3_file, text_path, json_path, output_dir, video_id)
            else:
                return self._parse_srt_vtt(output_dir, video_id, text_path, json_path)

        return "", ""

    @staticmethod
    def _parse_json3(json3_file: Path, text_path: Path, json_path: Path,
                     _output_dir: Path, _video_id: str) -> tuple[str, str]:
        """Parse YouTube json3 subtitle format with timed segments."""
        try:
            data = json.loads(json3_file.read_text(encoding="utf-8"))
            events = data.get("events", [])
            segments = []
            timed_segments = []
            for ev in events:
                t_start = ev.get("tStartMs", 0) / 1000.0
                for s in ev.get("segs", []):
                    text = s.get("utf8", "").strip()
                    if text:
                        segments.append(text)
                        timed_segments.append({"t": t_start, "text": text})
            if segments:
                txt = " ".join(segments)
                text_path.write_text(txt, encoding="utf-8")
                json_path.write_text(json.dumps(timed_segments, ensure_ascii=False), encoding="utf-8")
                return str(text_path), str(json_path)
        except (json.JSONDecodeError, KeyError, OSError):
            pass
        return "", ""

    @staticmethod
    def _parse_srt_vtt(output_dir: Path, video_id: str,
                       text_path: Path, json_path: Path) -> tuple[str, str]:
        """Parse SRT/VTT subtitle files."""
        raw_text = ""
        timed_data = []
        for ext in [".en.vtt", ".en.srt", ".vtt", ".srt"]:
            sub_path = output_dir / f"{video_id}{ext}"
            if not sub_path.exists():
                continue
            content = sub_path.read_text(encoding="utf-8")
            lines = []
            current = {}
            for line in content.split("\n"):
                line = line.strip()
                if not line or line.isdigit() or line.startswith("WEBVTT") \
                   or line.startswith("Kind:") or line.startswith("Language:"):
                    if "-->" in line:
                        parts = line.split("-->")
                        if len(parts) == 2:
                            current = {"start": parts[0].strip(), "text": ""}
                        continue
                    if current.get("text"):
                        lines.append(current["text"])
                        timed_data.append({"t": 0, "text": current["text"]})
                        current = {}
                    continue
                line = re.sub(r"<[^>]+>", "", line)
                if line:
                    if current:
                        current["text"] += " " + line if current["text"] else line
                    else:
                        lines.append(line)
            raw_text = "\n".join(lines)
            break

        if raw_text:
            text_path.write_text(raw_text, encoding="utf-8")
        if timed_data:
            json_path.write_text(json.dumps(timed_data, ensure_ascii=False), encoding="utf-8")
        return str(text_path) if raw_text else "", str(json_path) if timed_data else ""

    def run(self, item: ContentItem, config: dict[str, Any]) -> ContentItem:
        video_id = item.source_id
        output_dir = Path(config.get("output_dir", "output/raw"))
        output_dir.mkdir(parents=True, exist_ok=True)

        cookies = CookieManager(config.get("cookies_path"))
        proxy = ProxyManager(http=config.get("proxy_http"))

        # Fetch metadata
        meta = self._download_metadata(video_id, cookies, proxy)
        item.title = meta.get("title", item.title or "")
        item.source_url = f"https://www.youtube.com/watch?v={video_id}"
        item.source_metadata = {
            "author": meta.get("uploader", ""),
            "channel": meta.get("channel", ""),
            "published_at": meta.get("upload_date", ""),
            "duration": meta.get("duration", 0),
            "url": item.source_url,
            "view_count": meta.get("view_count", 0),
            "thumbnail": meta.get("thumbnail", ""),
            "description": (meta.get("description", "") or "")[:500],
        }

        # Fetch transcript
        text_path, json_path = self._download_transcript(video_id, output_dir, cookies, proxy)
        if text_path:
            item.raw_text = Path(text_path).read_text(encoding="utf-8")
            if not item.title and meta.get("title"):
                item.title = meta["title"]
        item.artifacts.raw_text = text_path
        item.artifacts.timed_transcript = json_path

        # Store cover image
        cover = item.source_metadata.get("thumbnail") or f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        item.artifacts.cover_img = cover

        logger.info(f"[youtube_extract] '{item.title}' — {len(item.raw_text)} chars transcript")
        return item


def create():
    return YouTubeExtract()