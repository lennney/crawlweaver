"""账号追踪采集器 — 从 tracked_accounts 表读取账号列表，逐账号抓最新视频。

用法：
    scout = AccountScout()
    videos = scout.scrape()  # 读取 DB 中 active 账号

支持平台：
    - TikTok: yt-dlp @username 频道提取（比 TikTokApi user API 更稳定）
    - YouTube: yt-dlp @username/videos 频道提取

⚠️ yt-dlp flat-playlist 模式下 YouTube 视频 view=0，
   如需准确数据请改用 `--no-flat-playlist`（更慢）。
"""

import json
import logging
import subprocess
from datetime import datetime, timezone, timedelta

import os

from trending_aggregator.protocol import Scout

logger = logging.getLogger(__name__)


# yt-dlp 输出中的字段 → 归一化字段映射
FIELD_MAP = {
    "view_count": "views",
    "like_count": "likes",
    "comment_count": "comments",
    "repost_count": "shares",
}


def _normalize_ytdlp(data: dict, platform: str) -> dict | None:
    """yt-dlp 输出 → 归一化 dict，返回 None 表示这条数据不可用。"""
    vid = data.get("id")
    if not vid:
        return None
    return {
        "id": f"{platform}:{vid}",
        "title": (data.get("title") or "")[:200],
        "url": data.get("webpage_url") or data.get("url", ""),
        "views": data.get("view_count") or 0,
        "likes": data.get("like_count") or 0,
        "comments": data.get("comment_count") or 0,
        "shares": data.get("repost_count") or 0,
        "duration": data.get("duration", 0),
        "tags": data.get("tags") or [],
        "description": data.get("description", ""),
        "thumbnail_url": _pick_thumbnail(data),
        "published_at": _parse_ts(data),
    }


def _pick_thumbnail(data: dict) -> str:
    thumbs = data.get("thumbnails") or []
    return thumbs[0]["url"] if thumbs else ""


def _parse_ts(data: dict) -> datetime | None:
    ts = data.get("timestamp")
    if ts:
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    # fallback: yt-dlp upload_date (YYYYMMDD)
    ud = data.get("upload_date")
    if ud and len(ud) == 8:
        try:
            return datetime.strptime(ud, "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


class AccountScout(Scout):
    """账号追踪采集器 — 从 DB 读账号，逐账号抓最新视频。"""

    platform = "account"

    def __init__(self, accounts: list[dict] | None = None, max_age_days: int = 30):
        """
        Args:
            accounts: [(platform, username), ...] 列表。
                      为 None 时从 DB tracked_accounts 表读取。
            max_age_days: 只拉取最近 N 天的视频。默认 30 天。
        """
        self._accounts = accounts
        self.max_age_days = max_age_days

    def scrape(self) -> list[dict]:
        account_objs = self._load_accounts() if self._accounts is None else self._accounts
        all_videos: list[dict] = []
        seen: set[str] = set()
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.max_age_days)
        account_stats: list[tuple[TrackedAccount, int, int]] = []  # (obj, video_count, views_sum)

        for acct in account_objs:
            if isinstance(acct, (list, tuple)):
                # 兼容 [(platform, username), ...] 格式
                platform, username = acct
                obj = None
            else:
                platform = acct.platform
                username = acct.username
                obj = acct

            try:
                videos = self._fetch_account(platform, username)
            except Exception:
                logger.error("账号 %s/%s 采集失败", platform, username, exc_info=True)
                continue

            account_videos = 0
            account_views = 0
            for v in videos:
                if v["id"] not in seen:
                    if v.get("published_at") and v["published_at"] < cutoff:
                        continue
                    seen.add(v["id"])
                    all_videos.append(v)
                    account_videos += 1
                    account_views += v.get("views", 0)

            if obj is not None:
                account_stats.append((obj, account_videos, account_views))

        # 更新 DB 中的 last_fetched_at 和 video_count
        if account_stats:
            self._update_account_stats(account_stats)

        logger.info(
            "Account: %s 个账号 → %s 条视频", len(account_objs), len(all_videos),
        )
        return all_videos

    def _update_account_stats(
        self, stats: list[tuple[TrackedAccount, int, int]]
    ) -> None:
        """更新账号的 last_fetched_at 和 video_count。"""
        from sqlalchemy import create_engine
        from factory.models import Base, get_session

        db_url = os.environ.get("DATABASE_URL", "sqlite:///dev.db")
        engine = create_engine(db_url)
        Base.metadata.create_all(engine)
        session = get_session(engine)
        try:
            now = datetime.now(timezone.utc)
            for acct, video_count, views_sum in stats:
                db_acct = session.get(TrackedAccount, acct.id)
                if db_acct:
                    db_acct.last_fetched_at = now
                    db_acct.video_count = video_count
            session.commit()
        finally:
            session.close()

    def _load_accounts(self) -> list:
        """从 DB tracked_accounts 表读取活跃账号，返回 TrackedAccount 对象列表。"""
        from sqlalchemy import create_engine
        from factory.models import Base, TrackedAccount, get_session

        db_url = os.environ.get("DATABASE_URL", "sqlite:///dev.db")
        engine = create_engine(db_url)
        Base.metadata.create_all(engine)
        session = get_session(engine)
        try:
            return list(session.query(TrackedAccount).filter_by(active=True).all())
        finally:
            session.close()

    def _fetch_account(self, platform: str, username: str) -> list[dict]:
        username = username.lstrip("@")
        if platform == "tiktok":
            url = f"https://www.tiktok.com/@{username}"
            return self._run_ytdlp(url, "tiktok")
        elif platform == "youtube":
            url = f"https://www.youtube.com/@{username}/videos"
            return self._run_ytdlp(url, "youtube")
        else:
            logger.warning("不支持的平台: %s", platform)
            return []

    def _run_ytdlp(self, url: str, platform: str, limit: int = 20) -> list[dict]:
        cmd = [
            "python3", "-m", "yt_dlp",
            url,
            "--dump-json",
            "--flat-playlist",
            "--playlist-end", str(limit),
            "--no-warnings",
            "--ignore-errors",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            logger.error("yt-dlp 超时: %s", url)
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
                v = _normalize_ytdlp(data, platform)
                if v:
                    videos.append(v)
            except (json.JSONDecodeError, KeyError):
                logger.warning("跳过损坏行")
        return videos
