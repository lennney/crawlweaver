"""Extract tool — pull raw content from YouTube/Web/Reddit.

Factor #4: Tool is just structured output from deterministic code.
No LLM involved — pure scraping.
"""

import logging
import re
import subprocess
from typing import Any

from state import CrawlState, Source, Step

logger = logging.getLogger("crawler.extract")


def extract(state: CrawlState) -> CrawlState:
    """Extract raw content from a URL. Dispatches by source type."""
    try:
        if state.source == Source.YOUTUBE:
            _extract_youtube(state)
        elif state.source == Source.WEB:
            _extract_web(state)
        elif state.source == Source.REDDIT:
            _extract_reddit(state)
        else:
            raise ValueError(f"Unknown source: {state.source}")

        state.step = Step.EXTRACTED
        state.append_event("extract", True, f"Extracted {len(state.raw_text)} chars")

    except Exception as e:
        state.error = str(e)
        state.append_event("extract", False, str(e))
        logger.error(f"Extract failed: {e}")

    return state


def _extract_youtube(state: CrawlState):
    """Extract YouTube transcript via yt-dlp."""
    url = state.url

    # Strategy 1: youtube-transcript-api (fast, no download needed)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        video_id = _youtube_id(url)
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # Try preferred language first, then fallback
        try:
            transcript = transcript_list.find_transcript(["en"])
        except Exception:
            transcript = transcript_list.find_manually_created_transcript(["zh-Hans", "zh", "en"])

        entries = transcript.fetch()
        state.raw_text = " ".join(e.get("text", "") for e in entries if e.get("text"))
        state.title = f"YouTube Video {video_id}"
        state.source_metadata = {"video_id": video_id, "method": "transcript_api"}
        return
    except Exception as e:
        logger.warning(f"Transcript API failed: {e}, trying yt-dlp")

    # Strategy 2: yt-dlp subtitle download
    try:
        result = subprocess.run(
            ["yt-dlp", "--skip-download", "--write-auto-sub", "--sub-lang", "en,zh",
             "--sub-format", "txt", "-o", "/tmp/yt_%(id)s", url],
            capture_output=True, text=True, timeout=60,
        )
        video_id = _youtube_id(url)
        import glob
        subs = glob.glob(f"/tmp/yt_{video_id}*.txt")
        if subs:
            state.raw_text = open(subs[0]).read()
            state.title = f"YouTube Video {video_id}"
            state.source_metadata = {"video_id": video_id, "method": "yt-dlp"}
            return
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
