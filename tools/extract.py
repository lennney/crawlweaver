"""Extract tool — pull raw content from YouTube/Web/Reddit.

Factor #4: Tool is just structured output from deterministic code.
No LLM involved — pure scraping.
"""

import logging
import re
import subprocess
from pathlib import Path

from state import CrawlState, Source, Step

logger = logging.getLogger("crawler.extract")


def extract(state: CrawlState) -> CrawlState:
    """Extract raw content from a URL. Dispatches by source type.

    Sprint 4: If state.preferred_extractor is set (from knowledge site_patterns),
    it overrides the default extractor for the source type.
    Sprint 5: Added Twitter, WeChat, Zhihu source types.
    """
    try:
        # Sprint 4: Use preferred extractor if knowledge suggests one
        preferred = state.preferred_extractor.lower().strip() if state.preferred_extractor else ""

        if state.source == Source.YOUTUBE and preferred != "web":
            _extract_youtube(state)
        elif state.source == Source.WEB or preferred == "web":
            _extract_web(state)
        elif state.source == Source.REDDIT:
            _extract_reddit(state)
        elif state.source == Source.TWITTER:
            from tools.extractors.twitter import extract_twitter

            extract_twitter(state)
        elif state.source == Source.WECHAT:
            from tools.extractors.wechat import extract_wechat

            extract_wechat(state)
        elif state.source == Source.ZHIHU:
            from tools.extractors.zhihu import extract_zhihu

            extract_zhihu(state)
        else:
            raise ValueError(f"Unknown source: {state.source}")

        state.step = Step.EXTRACTED
        state.append_event("extract", True, f"Extracted {len(state.raw_text)} chars")

    except Exception as e:
        state.error = str(e)
        state.append_event("extract", False, str(e))
        logger.error(f"Extract failed: {e}")

    return state


def detect_source(url: str) -> str:
    """Auto-detect source type from URL.

    Returns a Source enum value string. Useful for CLI --source auto-detection.
    Falls back to 'web' for unknown URLs.

    Sprint 5: Added Twitter, WeChat, Zhihu detection.
    """
    url_lower = url.lower()

    # YouTube
    if any(d in url_lower for d in ["youtube.com", "youtu.be"]):
        return "youtube"

    # Twitter/X
    if any(d in url_lower for d in ["twitter.com", "x.com"]):
        return "twitter"

    # WeChat
    if "mp.weixin.qq.com" in url_lower:
        return "wechat"

    # Zhihu
    if "zhihu.com" in url_lower:
        return "zhihu"

    # Reddit
    if "reddit.com" in url_lower:
        return "reddit"

    # Default: generic web
    return "web"


def _extract_youtube(state: CrawlState):
    """Extract YouTube transcript via yt-dlp."""
    url = state.url

    # Strategy 1: youtube-transcript-api (fast, no download needed)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        video_id = _youtube_id(url)
        api = YouTubeTranscriptApi()

        # New API (v1.x): api.fetch(video_id, languages=[...])
        # Returns iterable of FetchedTranscriptSnippet with .text attribute
        transcript = api.fetch(video_id, languages=["en", "zh-Hans", "zh"])
        state.raw_text = " ".join(snippet.text for snippet in transcript if snippet.text)
        state.title = f"YouTube Video {video_id}"
        state.source_metadata = {"video_id": video_id, "method": "transcript_api"}
        return
    except Exception as e:
        logger.warning(f"Transcript API failed: {e}, trying yt-dlp")

    # Strategy 2: yt-dlp with cookies
    try:
        # Look for cookies file — multiple possible locations
        cookies_path = None
        for candidate in [
            Path(__file__).parent.parent / "yt_cookies.txt",
            Path(__file__).parent.parent / "cookies.txt",
            Path.home() / "yt_cookies.txt",
        ]:
            if candidate.exists() and candidate.stat().st_size > 200:
                cookies_path = str(candidate)
                break

        cmd = [
            "yt-dlp",
            "--skip-download",
            "--write-auto-sub",
            "--sub-lang",
            "en,zh",
            "--sub-format",
            "vtt/best",
            "-o",
            "/tmp/yt_%(id)s",
        ]
        if cookies_path:
            cmd.extend(["--cookies", cookies_path])
            logger.info(f"Using cookies: {cookies_path}")
        else:
            # No cookies — try android client trick
            cmd.extend(["--extractor-args", "youtube:player_client=android"])
            logger.warning("No cookies file found, trying android client")

        cmd.append(url)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        video_id = _youtube_id(url)
        import glob

        subs = glob.glob(f"/tmp/yt_{video_id}*.vtt") + glob.glob(f"/tmp/yt_{video_id}*.txt")
        if subs:
            raw = Path(subs[0]).read_text(encoding="utf-8")
            # If VTT format, strip timestamps and headers
            if subs[0].endswith(".vtt"):
                raw = _parse_vtt(raw)
            state.raw_text = raw
            state.title = f"YouTube Video {video_id}"
            state.source_metadata = {
                "video_id": video_id,
                "method": "yt-dlp",
                "cookies": bool(cookies_path),
            }
            return
        else:
            logger.warning(f"yt-dlp produced no subtitles. stderr: {result.stderr[:200]}")
    except Exception as e:
        logger.warning(f"yt-dlp failed: {e}")

    raise RuntimeError(f"Could not extract transcript from {url}")


def _extract_web(state: CrawlState):
    """Extract web page content via requests + BeautifulSoup."""
    import requests
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    resp = requests.get(state.url, headers=headers, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove noise
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    title = soup.title.string if soup.title else ""
    body = soup.get_text(separator="\n", strip=True)

    state.title = title.strip()
    state.raw_text = body[:10000]
    state.source_metadata = {"method": "requests+bs4"}


def _extract_reddit(state: CrawlState):
    """Extract Reddit post + comments via JSON API."""
    import requests

    url = state.url.rstrip("/")
    if not url.endswith(".json"):
        url += ".json"

    headers = {"User-Agent": "CrawlerBot/1.0"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    post = data[0]["data"]["children"][0]["data"]
    state.title = post.get("title", "")
    state.raw_text = post.get("selftext", "")

    # Top comments
    comments = []
    for child in data[1]["data"]["children"][:10]:
        if child["kind"] == "t1":
            comments.append(child["data"].get("body", ""))
    if comments:
        state.raw_text += "\n\n## Comments\n" + "\n\n".join(comments)

    state.source_metadata = {"method": "reddit_json", "subreddit": post.get("subreddit", "")}


def _youtube_id(url: str) -> str:
    """Extract YouTube video ID from URL."""
    patterns = [
        r"(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:embed/)([a-zA-Z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    raise ValueError(f"Cannot parse YouTube ID from {url}")


def _parse_vtt(vtt: str) -> str:
    """Extract plain text from WebVTT subtitle format.

    Strips: WEBVTT header, timestamps, positioning tags, duplicate lines.
    """
    lines = vtt.split("\n")
    seen = set()
    result = []
    for line in lines:
        line = line.strip()
        # Skip header, empty lines, timestamps, positioning
        if (
            not line
            or line.startswith("WEBVTT")
            or line.startswith("Kind:")
            or line.startswith("Language:")
        ):
            continue
        if re.match(r"^\d{2}:\d{2}", line):
            continue
        if re.match(r"^\d+$", line):
            continue
        # Strip HTML/VTT tags
        line = re.sub(r"<[^>]+>", "", line)
        line = re.sub(r"align:start position:\d+%", "", line)
        line = line.strip()
        if line and line not in seen:
            seen.add(line)
            result.append(line)
    return " ".join(result)
