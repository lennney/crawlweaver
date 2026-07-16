"""观测平台协调器 — 注册 scouts，跑 scrape → score → store 流水线。"""
import logging
import os

from factory.models import get_engine, get_session
from trending_aggregator.protocol import Scout
from trending_aggregator.store import save_to_db

logger = logging.getLogger(__name__)


# 注册所有数据源
def _default_scouts() -> list[Scout]:
    from trending_aggregator.scouts.tiktok import TikTokScout
    from trending_aggregator.scouts.youtube import YouTubeScout
    return [YouTubeScout(), TikTokScout()]


def run_scout(scout: Scout) -> int:
    """跑单个 scout：抓取 → 入库，返回入库数。"""
    logger.info("开始采集 %s ...", scout.platform)
    videos = scout.scrape()
    if not videos:
        logger.warning("%s 未获取到任何视频", scout.platform)
        return 0

    db_url = os.environ.get("DATABASE_URL", "sqlite:///dev.db")
    engine = get_engine(db_url)
    session = get_session(engine)
    try:
        count = save_to_db(session, videos, platform=scout.platform)
        logger.info("%s 完成: %s 个视频入库", scout.platform, count)
        return count
    finally:
        session.close()


def run_all(scouts: list[Scout] | None = None) -> dict[str, int]:
    """跑全部 scouts，返回 {platform: count}。单个失败不中断其他。"""
    if scouts is None:
        scouts = _default_scouts()

    results = {}
    for scout in scouts:
        try:
            results[scout.platform] = run_scout(scout)
        except Exception as e:
            logger.error("%s 采集失败: %s", scout.platform, e)
            results[scout.platform] = 0
    return results
