"""独立模型 — 仅建 account_tracker 所需的表，不碰 factory.models。"""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Boolean, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


class TrackedAccount(Base):
    """追踪的账号"""
    __tablename__ = "tracked_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(20), nullable=False)
    username = Column(String(200), nullable=False)
    display_name = Column(String(200), nullable=True)
    category = Column(String(50), nullable=True)
    notes = Column(String(500), nullable=True)
    active = Column(Boolean, default=True)
    last_fetched_at = Column(DateTime, nullable=True)
    video_count = Column(Integer, default=0)
    follower_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class VideoSnapshot(Base):
    """视频指标快照 — 每次采集记一行，用于趋势分析。

    一条 video_id 有多行，按 fetched_at 排序就是该视频的指标变化曲线。
    """
    __tablename__ = "video_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String, nullable=False, index=True)       # platform:vid
    platform = Column(String(20), nullable=False)
    username = Column(String(200), nullable=True)                # 来源账号
    title = Column(String(200))
    url = Column(String)
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    duration = Column(Integer, default=0)
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    published_at = Column(DateTime, nullable=True)


class AccountSnapshot(Base):
    """账号粉丝数快照 — 每日一条，用于计算涨粉。"""
    __tablename__ = "account_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, nullable=False, index=True)
    platform = Column(String(20), nullable=False)
    username = Column(String(200), nullable=False)
    follower_count = Column(Integer, default=0)
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


def get_engine(db_url: str | None = None):
    if db_url is None:
        import os
        db_url = os.environ.get("DATABASE_URL", "sqlite:///dev.db")
    return create_engine(db_url)


def init_db(db_url: str | None = None):
    """建表（幂等）。"""
    engine = get_engine(db_url)
    Base.metadata.create_all(engine)
    return engine


def get_session(db_url: str | None = None):
    engine = init_db(db_url)
    return sessionmaker(bind=engine)()