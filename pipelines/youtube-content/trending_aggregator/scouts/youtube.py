"""YouTube 话题热门数据源。

通过 yt-dlp 搜索指定话题，获取该话题下最热门的视频。
需要浏览器 cookie（yt-dlp --cookies-from-browser chrome）。
"""

import json
import logging
import subprocess
from datetime import datetime, timezone

from trending_aggregator.protocol import Scout

logger = logging.getLogger(__name__)

# 默认搜索话题 — 每个话题搜 limit 条，结果去重
DEFAULT_TOPICS = [
    "trending music",
    "trending gaming",
    "trending tech",
    "trending movies",
    "trending news",
]


class YouTubeScout(Scout):
    """YouTube 话题热门采集器。

    不再依赖已关闭的 /feed/trending，改为按话题搜索。
    需要 yt-dlp + 浏览器 cookie。
    """

    platform = "youtube"

    def __init__(self, topics: list[str] | None = None, limit_per_topic: int = 10):
        self.topics = topics or DEFAULT_TOPICS
        self.limit = limit_per_topic

    def scrape(self) -> list[dict]:
        """搜每个话题 → 合并 → 去重，返回归一化视频列表。"""
        seen: set[str] = set()
        all_videos: list[dict] = []

        for topic in self.topics:
            count = self.limit
            videos = self._search(topic, count)
            for v in videos:
                if v["id"] not in seen:
                    seen.add(v["id"])
                    all_videos.append(v)
            logger.debug("搜索 '%s' → %s 条 (去重后)", topic, len([v for v in videos if v["id"] in seen]))

        logger.info("YouTube: %s 个话题 → %s 条视频", len(self.topics), len(all_videos))
        return all_videos

    def _search(self, query: str, count: int) -> list[dict]:
        """搜一个话题，返回归一化视频列表。"""
        cmd = [
            "python3", "-m", "yt_dlp",
            f"ytsearch{count}:{query}",
            "--dump-json",
            "--flat-playlist",
            "--no-warnings",
            "--ignore-errors",
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            logger.error("搜索超时: %s", query)
            return []

        if result.returncode != 0:
            logger.error("yt-dlp 失败: %s", result.stderr[:200])
            return []

        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                videos.append(self._normalize(data))
            except (json.JSONDecodeError, KeyError):
                logger.warning("跳过损坏行")

        return videos

    def _normalize(self, data: dict) -> dict:
        """yt-dlp 输出的 JSON → 归一化 dict。"""
        return {
            "id": f"youtube:{data['id']}",
            "title": data.get("title", ""),
            "url": data.get("webpage_url", ""),
            "views": data.get("view_count") or 0,
            "likes": data.get("like_count") or 0,
            "comments": data.get("comment_count") or 0,
            "shares": 0,
            "duration": data.get("duration", 0),
            "tags": data.get("tags") or [],
            "description": data.get("description", ""),
            "thumbnail_url": data.get("thumbnail", ""),
            "published_at": _parse_upload_date(data.get("upload_date")),
        }


def _parse_upload_date(date_str: str | None) -> datetime | None:
    """yt-dlp 的 upload_date 格式: YYYYMMDD"""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None