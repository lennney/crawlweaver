"""共享入库逻辑 — youtube/tiktok scout 共用，避免重复。"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from factory.models import TrendingVideo
from trending_aggregator.scorer import compute_trend_score


def save_to_db(session: Session, videos: list[dict], platform: str) -> int:
    """upsert 到 trending_videos，按 id 命中则更新，返回写入数。"""
    now = datetime.now(timezone.utc)
    count = 0
    for v in videos:
        days_ago = (
            (now - v["published_at"]).total_seconds() / 86400
            if v.get("published_at")
            else 0
        )
        score = compute_trend_score(
            views=v["views"],
            likes=v["likes"],
            comments=v["comments"],
            shares=v.get("shares", 0),
            published_days_ago=days_ago,
        )

        record = session.get(TrendingVideo, v["id"])
        if record:
            record.views = v["views"]
            record.likes = v["likes"]
            record.comments = v["comments"]
            record.shares = v.get("shares", 0)
            record.trend_score = score
        else:
            session.add(TrendingVideo(
                id=v["id"],
                platform=platform,
                title=v["title"],
                url=v.get("url"),
                views=v["views"],
                likes=v["likes"],
                comments=v["comments"],
                shares=v.get("shares", 0),
                duration=v.get("duration"),
                tags=v.get("tags") or [],
                description=v.get("description", ""),
                thumbnail_url=v.get("thumbnail_url"),
                published_at=v.get("published_at"),
                trend_score=score,
            ))
        count += 1
    session.commit()
    return count
