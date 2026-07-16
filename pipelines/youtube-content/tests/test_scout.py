"""采集器入库逻辑测试 — 用 SQLite in-memory，不依赖 docker/PG。"""
from datetime import datetime, timezone

from sqlalchemy import create_engine

from factory.models import Base, TrendingVideo, get_session
from trending_aggregator.store import save_to_db


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return get_session(engine)


def _video(**overrides):
    base = {
        "id": "youtube:test123",
        "title": "Test Video",
        "url": "https://youtube.com/watch?v=test123",
        "views": 10000, "likes": 500, "comments": 100, "shares": 20,
        "duration": 600,
        "tags": ["test"],
        "description": "Test",
        "thumbnail_url": "https://example.com/thumb.jpg",
        "published_at": datetime.now(timezone.utc),
    }
    base.update(overrides)
    return base


def test_save_new_video():
    session = _make_session()
    videos = [_video()]

    count = save_to_db(session, videos, platform="youtube")
    assert count == 1

    record = session.get(TrendingVideo, "youtube:test123")
    assert record is not None
    assert record.title == "Test Video"
    assert record.platform == "youtube"
    assert record.trend_score > 0


def test_update_existing():
    session = _make_session()
    save_to_db(session, [_video(id="youtube:test456", title="Old", views=1000)], platform="youtube")

    save_to_db(
        session,
        [_video(id="youtube:test456", title="Old", views=5000, likes=50)],
        platform="youtube",
    )

    record = session.get(TrendingVideo, "youtube:test456")
    assert record.views == 5000
    assert record.likes == 50


def test_tiktok_platform_tagged():
    session = _make_session()
    save_to_db(session, [_video(id="tiktok:abc", shares=200)], platform="tiktok")

    record = session.get(TrendingVideo, "tiktok:abc")
    assert record.platform == "tiktok"
    assert record.shares == 200


def test_no_published_at_uses_zero_decay():
    """published_at 缺失时不应崩，热度分仍按 views 等算出"""
    session = _make_session()
    save_to_db(session, [_video(published_at=None)], platform="youtube")

    record = session.get(TrendingVideo, "youtube:test123")
    assert record.trend_score >= 0
