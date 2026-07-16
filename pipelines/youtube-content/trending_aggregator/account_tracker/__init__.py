"""独立账号追踪模块 — 不依赖 factory.models / crewai / AI 管线。

单人依赖: yt-dlp（系统命令）, SQLAlchemy。
用法:
    from trending_aggregator.account_tracker import AccountScout
    scout = AccountScout()
    videos = scout.scrape()
"""
from .models import TrackedAccount, get_session, init_db
from .scout import AccountScout
