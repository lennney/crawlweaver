"""YouTube keyframe extraction via yt-dlp + ffmpeg with LLM step detection."""
from __future__ import annotations
import json
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ytarticle.core.base import BaseComponent
from ytarticle.core.schema import ContentItem, ImageInfo
from ytarticle.support.cookies import CookieManager
from ytarticle.support.proxy import ProxyManager
from ytarticle.support.llm import call_llm

logger = logging.getLogger("ytarticle.youtube_frames")


class YouTubeFrames(BaseComponent):
    name = "youtube_frames"
    version = "2.0.0"
    required_fields = ["source_id", "article_md"]
    output_fields = ["images"]

    DETECT_STEPS_PROMPT = """You are a video analysis assistant. Given a DIY tutorial article and a timestamped transcript from the source video, match each article step to the closest transcript timestamp.

Return ONLY a JSON array matching each step to a timestamp:
[{"step": 1, "label": "Step description", "timestamp": "00:01:30"}]

Rules:
- Map each article step to the transcript segment where that action is first described
- Timestamp format: HH:MM:SS
- If you cannot confidently match a step, use the transcript segment closest in topic
- Skip steps that have no clear transcript match"""

    @staticmethod
    def _find_deno() -> str:
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
        deno = YouTubeFrames._find_deno()
        if deno:
            return ["--js-runtimes", f"deno:{deno}", "--remote-components", "ejs:github"]
        return []

    def run(self, item: ContentItem, config: dict[str, Any]) -> ContentItem:
        if item.source.value != "youtube" or not item.source_id:
            return item

        if not shutil.which("ffmpeg"):
            logger.warning("[youtube_frames] ffmpeg not found — skipping")
            return item

        video_id = item.source_id
        output_dir = Path(config.get("output_dir", "output/images")) / video_id
        output_dir.mkdir(parents=True, exist_ok=True)

        cookies = CookieManager(config.get("cookies_path"))
        proxy = ProxyManager(http=config.get("proxy_http"))

        # Step 1: Detect timestamps via LLM
        timestamps = self._detect_timestamps(item.article_md, item.artifacts.timed_transcript)

        # Step 2: Download video (480p)
        video_path = self._download_video(video_id, output_dir, cookies, proxy)

        # Step 3: Extract frames
        MIN_FRAMES = 5
        if video_path and timestamps:
            frames = self._extract_frames(video_path, timestamps, output_dir)
            # Fallback fill: if LLM detected too few frames, supplement
            if len(frames) < MIN_FRAMES and video_path.exists():
                need = MIN_FRAMES - len(frames)
                used_steps = {f["step"] for f in frames}
                extra_frames = self._fallback_frames(video_path, need + len(frames), output_dir)
                extra_frames = [f for f in extra_frames if f["step"] not in used_steps][:need]
                frames += extra_frames
                logger.info(f"[youtube_frames] Supplemented {len(extra_frames)} fallback frames (total: {len(frames)})")
            elif len(frames) < MIN_FRAMES:
                logger.info(f"[youtube_frames] Only {len(frames)} frames extracted (video gone, can't supplement)")
        elif video_path:
            step_count = len(re.findall(r"^### Step \d", item.article_md, re.MULTILINE))
            if step_count == 0:
                step_count = len(re.findall(r"^## Step \d", item.article_md, re.MULTILINE))
            if step_count == 0:
                step_count = 8
            logger.info(f"[youtube_frames] Using fallback: {step_count} intervals")
            frames = self._fallback_frames(video_path, step_count, output_dir)
        else:
            frames = []

        # Clean up video
        if video_path and video_path.exists():
            video_path.unlink(missing_ok=True)

        for f in frames:
            item.images.append(ImageInfo(
                path=f["path"],
                alt=f.get("alt", f"Step {f['step']}"),
                step=f["step"],
            ))

        item.artifacts.images_dir = str(output_dir)
        return item

    def _detect_timestamps(self, article_md: str, timed_path: str) -> list[dict]:
        if not timed_path or not Path(timed_path).exists():
            logger.info("[youtube_frames] No timed transcript — skipping stamp detection")
            return []

        # Extract steps section
        steps_section = ""
        in_steps = False
        for line in article_md.split("\n"):
            if re.match(r"^##\s*Step", line, re.IGNORECASE):
                in_steps = True
            if in_steps and line.startswith("## ") and "Step" not in line:
                break
            if in_steps:
                steps_section += line + "\n"
        if not steps_section.strip():
            return []

        try:
            timed_data = json.loads(Path(timed_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"[youtube_frames] Failed to load timed transcript: {e}")
            return []

        timed_sample = timed_data[::3][:80]  # every 3rd, max 80

        user_prompt = (
            f"Article steps:\n{steps_section.strip()}\n\n"
            f"Transcript segments:\n{json.dumps(timed_sample, ensure_ascii=False)}"
        )

        logger.info("[youtube_frames] Detecting step timestamps via LLM...")
        try:
            result = call_llm(self.DETECT_STEPS_PROMPT, user_prompt, max_tokens=2048, temperature=0.3)
            json_match = re.search(r"\[.*\]", result, re.DOTALL)
            if json_match:
                stamps = json.loads(json_match.group())
                logger.info(f"[youtube_frames] Detected {len(stamps)} step timestamps")
                return stamps
        except Exception as e:
            logger.warning(f"[youtube_frames] Timestamp detection failed: {e}")
        return []

    def _download_video(self, video_id: str, output_dir: Path,
                        cookies: CookieManager, proxy: ProxyManager) -> Path | None:
        video_path = output_dir / f"{video_id}.mp4"
        if video_path.exists():
            logger.info(f"[youtube_frames] Video already downloaded: {video_id}")
            return video_path

        logger.info(f"[youtube_frames] Downloading video {video_id} (480p)...")
        cmd = [sys.executable, "-m", "yt_dlp",
               "-f", "bestvideo[height<=480]",
               *cookies.yt_dlp_args(),
               *proxy.yt_dlp_args(),
               *self._js_flags(),
               "--impersonate", "chrome",
               "-o", str(video_path),
               f"https://www.youtube.com/watch?v={video_id}"]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            logger.warning(f"[youtube_frames] Download timed out for {video_id}")
            return None
        except OSError as e:
            logger.warning(f"[youtube_frames] Download error: {e}")
            return None

        if result.returncode != 0 or not video_path.exists():
            logger.warning(f"[youtube_frames] Download failed: {result.stderr[-200:]}")
            return None
        return video_path

    def _extract_frames(self, video_path: Path, timestamps: list[dict],
                        output_dir: Path) -> list[dict]:
        ts_pattern = re.compile(r"^\d{2}:\d{2}:\d{2}$")
        frames = []
        for item in timestamps:
            ts = item.get("timestamp", "")
            if not ts_pattern.match(ts):
                continue
            step = item.get("step", len(frames) + 1)
            frame_path = output_dir / f"step_{step:02d}.jpg"
            try:
                result = subprocess.run(
                    ["ffmpeg", "-ss", ts, "-i", str(video_path),
                     "-frames:v", "1", "-q:v", "2",
                     "-filter:v", "scale=800:-1",
                     "-y", str(frame_path)],
                    capture_output=True, text=True, timeout=30)
            except (FileNotFoundError, OSError):
                continue
            if result.returncode == 0 and frame_path.exists():
                frames.append({"path": str(frame_path),
                              "alt": item.get("label", f"Step {step}"),
                              "step": step})
                logger.info(f"[youtube_frames] Extracted: {frame_path.name}")
        return frames

    def _fallback_frames(self, video_path: Path, num_steps: int,
                         output_dir: Path) -> list[dict]:
        if not shutil.which("ffprobe"):
            return []
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration", "-of", "json", str(video_path)],
            capture_output=True, text=True, timeout=15)
        try:
            duration = float(json.loads(result.stdout).get("format", {}).get("duration", 600))
        except (json.JSONDecodeError, KeyError, ValueError):
            duration = 600

        interval = duration / (num_steps + 1)
        frames = []
        for i in range(1, num_steps + 1):
            t = int(interval * i)
            mm, ss = divmod(t, 60)
            hh, mm = divmod(mm, 60)
            ts = f"{hh:02d}:{mm:02d}:{ss:02d}"
            frame_path = output_dir / f"step_{i:02d}.jpg"
            try:
                result = subprocess.run(
                    ["ffmpeg", "-ss", ts, "-i", str(video_path),
                     "-frames:v", "1", "-q:v", "2",
                     "-filter:v", "scale=800:-1",
                     "-y", str(frame_path)],
                    capture_output=True, text=True, timeout=30)
            except (FileNotFoundError, OSError):
                continue
            if result.returncode == 0 and frame_path.exists():
                frames.append({"path": str(frame_path), "alt": f"Step {i}", "step": i})
        return frames


def create():
    return YouTubeFrames()