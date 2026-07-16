"""YouTube #tag 搜索采集器 — 按 tag 列表搜热门视频，过滤 + 语言检测。

用法：
    scout = YouTubeTagScout(tags=["movie", "kdrama"])
    videos = scout.scrape()

依赖：yt-dlp（系统级命令）
"""

import json
import logging
import subprocess
from datetime import datetime, timezone, timedelta

from trending_aggregator.protocol import Scout
from trending_aggregator.scouts.language_filter import is_target_language

logger = logging.getLogger(__name__)

MIN_VIEWS = 500_000
MIN_LIKES = 30_000
MAX_AGE_DAYS = 30


class YouTubeTagScout(Scout):
    """YouTube #tag 搜索采集器。

    用 yt-dlp ytsearch 搜每个 tag，再过滤播放量/点赞/时间窗口/语言。
    ytsearch 返回的是按相关度排序的结果，天然偏向高播内容。
    """

    platform = "youtube"

    def __init__(
        self,
        tags: list[str],
        min_views: int = MIN_VIEWS,
        min_likes: int = MIN_LIKES,
        max_age_days: int = MAX_AGE_DAYS,
        language_filter: bool = True,
        videos_per_tag: int = 30,
        max_duration: int | None = None,  # 设 120 只抓 Shorts（< 2min）
    ):
        self.tags = [t.lstrip("#") for t in tags]
        self.min_views = min_views
        self.min_likes = min_likes
        self.max_age_days = max_age_days
        self.language_filter = language_filter
        self.videos_per_tag = videos_per_tag
        self.max_duration = max_duration

    def scrape(self) -> list[dict]:
        seen: set[str] = set()
        results: list[dict] = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.max_age_days)

        for tag in self.tags:
            videos = self._search(tag)
            for v in videos:
                vid = v["id"]
                if vid in seen:
                    continue
                seen.add(vid)

                # 过阈值
                if not (v["views"] >= self.min_views or v["likes"] >= self.min_likes):
                    continue
                # 时间窗口
                if v["published_at"] and v["published_at"] < cutoff:
                    continue
                # 语言过滤
                if self.language_filter and not is_target_language(v["title"], v["description"]):
                    continue
                results.append(v)

        logger.info(
            "YouTube tag: %s 个 tag → %s 条命中",
            len(self.tags), len(results),
        )
        return results

    def _search(self, tag: str) -> list[dict]:
        """搜一个 tag，返回归一化视频列表。"""
        cmd = [
            "python3", "-m", "yt_dlp",
            f"ytsearch{self.videos_per_tag}:#{tag}",
            "--dump-json",
            "--flat-playlist",
            "--no-warnings",
            "--ignore-errors",
        ]
        if self.max_duration:
            cmd += ["--match-filter", f"duration < {self.max_duration}"]
        # 时间过滤 — 传给 yt-dlp 在搜索层过滤，避免 flat-playlist 下 upload_date 为空
        date_after = (
            datetime.now(timezone.utc) - timedelta(days=self.max_age_days)
        ).strftime("%Y%m%d")
        cmd += ["--dateafter", date_after]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            logger.error("YouTube 搜索超时: #%s", tag)
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
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
