"""TikTok 热门数据源。

通过 TikTokApi（davidteather/TikTok-Api）获取 TikTok 热门视频。
需要 Playwright + chromium（首次运行会自动下载）。
"""

import asyncio
import logging
from datetime import datetime, timezone

from TikTokApi import TikTokApi

from trending_aggregator.protocol import Scout

logger = logging.getLogger(__name__)


class TikTokScout(Scout):
    """TikTok 热门采集器 — 使用 TikTokApi 获取 For You 热门视频。"""

    platform = "tiktok"

    def __init__(self, limit: int = 30, headless: bool = True):
        self.limit = limit
        self.headless = headless

    def scrape(self) -> list[dict]:
        """获取 TikTok 热门视频，返回归一化列表。"""
        return asyncio.run(self._scrape_async())

    async def _scrape_async(self) -> list[dict]:
        videos: list[dict] = []
        async with TikTokApi() as api:
            await api.create_sessions(
                num_sessions=1,
                headless=self.headless,
            )
            async for video in api.trending.videos(count=self.limit):
                try:
                    videos.append(self._normalize(video))
                except Exception:
                    logger.warning("跳过 TikTok 视频 %s", getattr(video, "id", "?"))
        logger.info("TikTok: 获取 %s 条热门视频", len(videos))
        return videos

    def _normalize(self, video) -> dict:
        data = video.as_dict
        stats = video.stats or {}
        author = data.get("author", {}) or {}

        # TikTokApi v7 statsV2 字段名: playCount, diggCount, shareCount, commentCount
        # 兼容 stats 旧格式
        def _s(key: str, *aliases: str) -> int:
            for k in (key, *aliases):
                v = stats.get(k)
                if v is not None:
                    return int(v)
            return 0

        uid = data.get("id", "")
        author_id = author.get("uniqueId", "") if isinstance(author, dict) else ""

        return {
            "id": f"tiktok:{uid}",
            "title": (data.get("desc") or "")[:200],
            "url": f"https://www.tiktok.com/@{author_id}/video/{uid}" if author_id else "",
            "views": _s("playCount", "play_count", "viewCount"),
            "likes": _s("diggCount", "digg_count", "likeCount"),
            "comments": _s("commentCount", "comment_count"),
            "shares": _s("shareCount", "share_count"),
            "duration": (data.get("video") or {}).get("duration", 0),
            "tags": [h.get("title", "") for h in (data.get("challenges") or [])],
            "description": data.get("desc", ""),
            "thumbnail_url": (data.get("video") or {}).get("cover", ""),
            "published_at": (
                datetime.fromtimestamp(data["createTime"], tz=timezone.utc)
                if data.get("createTime")
                else None
            ),
        }