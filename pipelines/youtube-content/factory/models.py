""""数据库模型 — YouTube Content Factory"""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


class PipelineStage(str, enum.Enum):
    IDEA = "idea"
    BRIEFED = "briefed"
    PRODUCING = "producing"
    PRODUCED = "produced"
    SEO_DONE = "seo_done"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    PUBLISHING = "publishing"
    LIVE = "live"
    FAILED = "failed"


class TrendingVideo(Base):
    """每日热门视频（YouTube + TikTok）"""
    __tablename__ = "trending_videos"

    id = Column(String, primary_key=True)          # platform:video_id
    platform = Column(String, nullable=False)       # youtube / tiktok
    title = Column(String, nullable=False)
    url = Column(String)
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    duration = Column(Integer)                      # 秒
    tags = Column(JSON, default=list)
    description = Column(Text)
    thumbnail_url = Column(String)
    published_at = Column(DateTime, nullable=True)
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    trend_score = Column(Float, default=0.0)


class Video(Base):
    """生产的视频"""
    __tablename__ = "videos"

    id = Column(String, primary_key=True)
    stage = Column(Enum(PipelineStage), nullable=False, default=PipelineStage.IDEA)
    title = Column(String)
    hook_angle = Column(String)
    source_trend_id = Column(String, ForeignKey("trending_videos.id"))
    platform = Column(String, nullable=False)

    # 素材
    material_path = Column(String)
    output_path = Column(String)

    # SEO
    seo_package = Column(JSON)

    # 审核
    review_status = Column(String, nullable=True)  # pending/approved/rejected
    review_notes = Column(Text, nullable=True)

    # 发布
    youtube_id = Column(String)
    scheduled_publish_at = Column(DateTime, nullable=True)

    # 分析（Phase 2+）
    analytics = Column(JSON, nullable=True)

    # 元数据
    crew_run_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, onupdate=lambda: datetime.now(timezone.utc))
    error = Column(Text)


class TrackedTag(Base):
    """追踪的 #tag 列表（可动态增删）"""
    __tablename__ = "tracked_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tag = Column(String(100), nullable=False, unique=True)
    platform = Column(String(20), nullable=False, default="all")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class TrackedAccount(Base):
    """追踪的账号"""
    __tablename__ = "tracked_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(20), nullable=False)
    username = Column(String(200), nullable=False)
    display_name = Column(String(200), nullable=True)
    category = Column(String(50), nullable=True)       # kdrama, movie, brand, ...
    notes = Column(String(500), nullable=True)          # 粉丝数、频道描述等备注
    active = Column(Boolean, default=True)
    last_fetched_at = Column(DateTime, nullable=True)
    video_count = Column(Integer, default=0)            # 上次采集到的视频总数
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def get_engine(db_url: str):
    return create_engine(db_url, pool_size=5, max_overflow=10)


def get_session(engine):
    return sessionmaker(bind=engine)()
