"""TikTok 按关键词匹配采集器 — 从热门视频中筛选内容。

策略：
1. 从 For You 热门拉取 N 条视频（trending endpoint 实测可用）
2. 按关键词列表匹配（视频描述或标签中包含关键词）
3. 过阈值（播放量/点赞/时间/语言）

⚠️ 已知限制：
- TikTok 对 hashtag/search API 反爬严格，无法直接按 tag 搜索
- 本采集器从 trending feed 按文本关键词过滤，命中率受 trending 内容分布影响
- 后续升级：代理轮换 + 多 session + 付费 API 可提升覆盖率和准确率
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from TikTokApi import TikTokApi

from trending_aggregator.protocol import Scout
from trending_aggregator.scouts.language_filter import is_target_language

logger = logging.getLogger(__name__)

MIN_VIEWS = 500_000
MIN_LIKES = 30_000
MAX_AGE_DAYS = 30


class TikTokTagScout(Scout):
    """TikTok 热门视频按关键词筛选采集器。"""

    platform = "tiktok"

    def __init__(
        self,
        tags: list[str],
        min_views: int = MIN_VIEWS,
        min_likes: int = MIN_LIKES,
        max_age_days: int = MAX_AGE_DAYS,
        language_filter: bool = True,
        headless: bool = True,
        max_videos: int = 100,
    ):
        self.keywords = {t.lstrip("#").lower() for t in tags}
        self.min_views = min_views
        self.min_likes = min_likes
        self.max_age_days = max_age_days
        self.language_filter = language_filter
        self.headless = headless
        self.max_videos = max_videos

    def scrape(self) -> list[dict]:
        return asyncio.run(self._scrape_async())

    async def _scrape_async(self) -> list[dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.max_age_days)
        results: list[dict] = []

        async with TikTokApi() as api:
            await api.create_sessions(
                num_sessions=1, headless=self.headless, sleep_after=2,
            )

            async for video in api.trending.videos(count=self.max_videos):
                v = self._normalize(video)
                if not self._matches_keywords(v):
                    continue
                if not self._pass_threshold(v):
                    continue
                if v["published_at"] and v["published_at"] < cutoff:
                    continue
                if self.language_filter and not is_target_language(v["title"], v["description"]):
                    continue
                results.append(v)

        logger.info(
            "TikTok tag: scanned %s trending → %s 条匹配关键词 %s",
            self.max_videos, len(results), sorted(self.keywords),
        )
        return results

    def _matches_keywords(self, v: dict) -> bool:
        """视频标签/描述中是否包含目标关键词。"""
        desc_lower = v["description"].lower()
        for kw in self.keywords:
            if kw in desc_lower:
                return True
            for tag in v["tags"]:
                if kw in tag.lower():
                    return True
        return False

    def _normalize(self, video) -> dict:
        data = video.as_dict
        stats = video.stats or {}
        author = data.get("author", {}) or {}

        def _s(key: str, *aliases: str) -> int:
            for k in (key, *aliases):
                if stats.get(k) is not None:
                    return int(stats[k])
            return 0

        uid = data.get("id", "")
        author_id = author.get("uniqueId", "") if isinstance(author, dict) else ""
        return {
            "id": f"tiktok:{uid}",
            "title": (data.get("desc") or "")[:200],
            "url": f"https://www.tiktok.com/@{author_id}/video/{uid}" if author_id else "",
            "views": _s("playCount", "viewCount"),
            "likes": _s("diggCount", "likeCount"),
            "comments": _s("commentCount"),
            "shares": _s("shareCount"),
            "duration": (data.get("video") or {}).get("duration", 0),
            "tags": [h.get("title", "") for h in (data.get("challenges") or [])],
            "description": data.get("desc", ""),
            "thumbnail_url": (data.get("video") or {}).get("cover", ""),
            "published_at": (
                datetime.fromtimestamp(data["createTime"], tz=timezone.utc)
                if data.get("createTime") else None
            ),
        }

    @staticmethod
    def _pass_threshold(v: dict) -> bool:
        return v["views"] >= MIN_VIEWS or v["likes"] >= MIN_LIKES
