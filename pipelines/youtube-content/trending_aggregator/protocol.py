"""Scout 协议 — 定义观测平台数据源接口。

每个数据源（YouTube、TikTok 等）只需实现 scrape() 返回归一化 dict 列表，
剩下的评分、入库、编排由 orchestrator 负责。
"""

from abc import ABC, abstractmethod


class Scout(ABC):
    """数据源抽象 — 加新平台只需实现这一个类。"""

    platform: str  # "youtube" / "tiktok" / ...

    @abstractmethod
    def scrape(self) -> list[dict]:
        """抓取热门视频，返回归一化 dict 列表。

        每个 dict 必须包含：
            id, title, url, views, likes, comments, shares,
            duration, tags, description, thumbnail_url, published_at
        """
        ...
