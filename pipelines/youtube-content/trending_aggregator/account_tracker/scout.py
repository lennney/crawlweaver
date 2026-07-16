"""账号采集器 — 纯采集逻辑，无外部依赖（除 yt-dlp）。

改进 v2:
  - --detailed 模式: YouTube 关 flat-playlist 获取真实 views/likes/comments
  - 每次采集自动写 VideoSnapshot 快照，支持趋势分析
  - 增量感知: 返回 new / updated / total 统计
"""
import json
import logging
import re
import subprocess
import urllib.request
from datetime import datetime, timezone, timedelta

from .models import TrackedAccount, VideoSnapshot, get_session

logger = logging.getLogger(__name__)


def _normalize(data: dict, platform: str) -> dict | None:
    vid = data.get("id")
    if not vid:
        return None
    thumbs = data.get("thumbnails") or []
    ts = data.get("timestamp")
    published = None
    if ts:
        published = datetime.fromtimestamp(ts, tz=timezone.utc)
    else:
        ud = data.get("upload_date")
        if ud and len(ud) == 8:
            try:
                published = datetime.strptime(ud, "%Y%m%d").replace(tzinfo=timezone.utc)
            except ValueError:
                pass
    return {
        "id": f"{platform}:{vid}",
        "platform": platform,
        "title": (data.get("title") or "")[:200],
        "url": data.get("webpage_url") or data.get("url", ""),
        "views": data.get("view_count") or 0,
        "likes": data.get("like_count") or 0,
        "comments": data.get("comment_count") or 0,
        "shares": data.get("repost_count") or 0,
        "duration": data.get("duration", 0),
        "tags": data.get("tags") or [],
        "description": data.get("description", ""),
        "thumbnail_url": thumbs[0]["url"] if thumbs else "",
        "published_at": published,
    }


class AccountScout:
    """账号采集器 — 从 DB 读账号列表 → yt-dlp 逐账号抓 → 写快照 → 写回统计。"""

    def __init__(self, max_age_days: int = 30, detailed: bool = False):
        """
        Args:
            max_age_days: 只拉取最近 N 天的视频。
            detailed: True 时 YouTube 用 --no-flat-playlist（真实 views/likes，慢 5-10x）。
        """
        self.max_age_days = max_age_days
        self.detailed = detailed

    def scrape(self) -> list[dict]:
        session = get_session()
        try:
            accounts = list(session.query(TrackedAccount).filter_by(active=True).all())
        finally:
            session.close()

        all_videos: list[dict] = []
        seen: set[str] = set()
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.max_age_days)
        stats: list[tuple[TrackedAccount, int]] = []

        for acct in accounts:
            try:
                videos = self._fetch_account(acct.platform, acct.username)
            except Exception:
                logger.error("采集失败 %s/%s", acct.platform, acct.username, exc_info=True)
                continue

            count = 0
            for v in videos:
                if v["id"] in seen:
                    continue
                if v.get("published_at") and v["published_at"] < cutoff:
                    continue
                seen.add(v["id"])
                v["username"] = acct.username
                all_videos.append(v)
                count += 1
            stats.append((acct, count))

        # 写入快照 + 增量统计
        incr = self._write_snapshots(all_videos)
        self._update_stats(stats)
        self._write_follower_snapshots(accounts)

        logger.info(
            "Account: %s 个账号 → %s 条视频 (new=%s, updated=%s)",
            len(accounts), incr["total"], incr["new"], incr["updated"],
        )
        return all_videos

    def _write_snapshots(self, videos: list[dict]) -> dict:
        """写入 VideoSnapshot，返回 {new, updated, total}。"""
        session = get_session()
        try:
            new = updated = 0
            now = datetime.now(timezone.utc)
            for v in videos:
                # 查该视频上次快照
                last = (
                    session.query(VideoSnapshot)
                    .filter_by(video_id=v["id"])
                    .order_by(VideoSnapshot.fetched_at.desc())
                    .first()
                )
                if last is None:
                    new += 1
                elif last.views != v["views"] or last.likes != v["likes"]:
                    updated += 1

                session.add(
                    VideoSnapshot(
                        video_id=v["id"],
                        platform=v.get("platform", ""),
                        username=v.get("username", ""),
                        title=v.get("title", ""),
                        url=v.get("url", ""),
                        views=v.get("views", 0),
                        likes=v.get("likes", 0),
                        comments=v.get("comments", 0),
                        shares=v.get("shares", 0),
                        duration=v.get("duration", 0),
                        published_at=v.get("published_at"),
                        fetched_at=now,
                    )
                )
            session.commit()
            return {"new": new, "updated": updated, "total": len(videos)}
        finally:
            session.close()

    def _update_stats(self, stats: list[tuple[TrackedAccount, int]]) -> None:
        session = get_session()
        try:
            now = datetime.now(timezone.utc)
            for acct, count in stats:
                db = session.get(TrackedAccount, acct.id)
                if db:
                    db.last_fetched_at = now
                    db.video_count = count
            session.commit()
        finally:
            session.close()

    def _fetch_account(self, platform: str, username: str) -> list[dict]:
        username = username.lstrip("@")
        if platform == "tiktok":
            url = f"https://www.tiktok.com/@{username}"
        elif platform == "youtube":
            url = self._yt_channel_url(username)
        elif platform == "instagram":
            return self._fetch_instagram_account(username)
        else:
            logger.warning("不支持的平台: %s", platform)
            return []
        videos = self._run_ytdlp(url, platform)
        # fallback: 有些频道没有 /videos tab，试不带后缀
        if not videos and platform == "youtube" and "/videos" in url:
            fallback = url.replace("/videos", "")
            logger.info("无 /videos tab，回退 %s", fallback)
            videos = self._run_ytdlp(fallback, platform)
        return videos

    @staticmethod
    def _yt_channel_url(username: str) -> str:
        """YouTube 频道 URL: @handle 或 /channel/UC..."""
        if username.startswith("UC") and len(username) == 24:
            return f"https://www.youtube.com/channel/{username}/videos"
        return f"https://www.youtube.com/@{username}/videos"

    def _run_ytdlp(self, url: str, platform: str, limit: int = 20) -> list[dict]:
        if platform == "youtube" and self.detailed:
            # ponytail: 关 flat-playlist 获取真实 views/likes，慢但准
            cmd = [
                "python3", "-m", "yt_dlp",
                url,
                "--dump-json",
                "--no-flat-playlist",
                "--playlist-end", str(limit),
                "--no-warnings",
                "--ignore-errors",
            ]
        else:
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
                v = _normalize(data, platform)
                if v:
                    videos.append(v)
            except (json.JSONDecodeError, KeyError):
                logger.warning("跳过损坏行")
        return videos

    def _write_follower_snapshots(self, accounts: list[TrackedAccount]) -> None:
        """拉取每个账号的粉丝数，写入 AccountSnapshot + 更新 TrackedAccount.follower_count。"""
        from .models import AccountSnapshot

        session = get_session()
        now = datetime.now(timezone.utc)
        try:
            for acct in accounts:
                count = self._fetch_follower_count(acct.platform, acct.username)
                if count is None:
                    continue
                # 写入每日快照
                session.add(AccountSnapshot(
                    account_id=acct.id,
                    platform=acct.platform,
                    username=acct.username,
                    follower_count=count,
                    fetched_at=now,
                ))
                # 更新账号最新粉丝数
                db = session.get(TrackedAccount, acct.id)
                if db:
                    db.follower_count = count
            session.commit()
        finally:
            session.close()

    def _fetch_follower_count(self, platform: str, username: str) -> int | None:
        """从频道页提取粉丝数。"""
        username = username.lstrip("@")
        if platform == "youtube":
            return self._fetch_youtube_followers(username)
        elif platform == "tiktok":
            return self._fetch_tiktok_followers(username)
        elif platform == "instagram":
            return self._fetch_instagram_followers(username)
        else:
            return None

    def _fetch_youtube_followers(self, username: str) -> int | None:
        """yt-dlp 抓 YouTube 频道页，从 channel_follower_count 取粉丝数。"""
        url = self._yt_channel_url(username).replace("/videos", "")
        cmd = [
            "python3", "-m", "yt_dlp",
            url,
            "--dump-json",
            "--playlist-end", "1",
            "--no-warnings",
            "--ignore-errors",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            logger.error("YT 粉丝数超时: %s", username)
            return None
        if result.returncode != 0:
            return None
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                fc = data.get("channel_follower_count")
                if fc is not None:
                    return int(fc)
            except (json.JSONDecodeError, KeyError, ValueError):
                pass
        return None

    def _fetch_tiktok_followers(self, username: str) -> int | None:
        """HTTP 抓取 TikTok 个人页，从 __UNIVERSAL_DATA_FOR_REHYDRATION__ 提取粉丝数。"""
        url = f"https://www.tiktok.com/@{username}"
        req = urllib.request.Request(url, headers={
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        })
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            html = resp.read().decode()
        except Exception:
            logger.error("TikTok 粉丝数请求失败: %s", username)
            return None

        m = re.search(
            r'<script[^>]*id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
            html,
        )
        if not m:
            logger.warning("TikTok UDFR 未找到: %s", username)
            return None
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            logger.warning("TikTok UDFR JSON 解析失败: %s", username)
            return None

        # 递归查找 followerCount
        def find_fc(obj, depth=0):
            if depth > 12:
                return None
            if isinstance(obj, dict):
                if "followerCount" in obj:
                    return obj["followerCount"]
                for v in obj.values():
                    r = find_fc(v, depth + 1)
                    if r is not None:
                        return r
            elif isinstance(obj, list):
                for item in obj:
                    r = find_fc(item, depth + 1)
                    if r is not None:
                        return r
            return None

        fc = find_fc(data)
        if fc is not None:
            return int(fc)
        return None

    # ---- Instagram ----

    IG_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
        ),
        "X-IG-App-ID": "936619743392459",
    }

    def _ig_request(self, path: str) -> dict | None:
        """Instagram API 请求，返回 JSON 或 None。"""
        url = f"https://www.instagram.com{path}"
        req = urllib.request.Request(url, headers=self.IG_HEADERS)
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            return json.loads(resp.read())
        except Exception:
            logger.error("IG API 失败: %s", path, exc_info=True)
            return None

    def _ig_user_id(self, username: str) -> str | None:
        """从 username 获取 Instagram user ID。"""
        data = self._ig_request(f"/api/v1/users/web_profile_info/?username={username}")
        if not data:
            return None
        return data.get("data", {}).get("user", {}).get("id")

    def _fetch_instagram_followers(self, username: str) -> int | None:
        """Instagram 粉丝数。"""
        data = self._ig_request(f"/api/v1/users/web_profile_info/?username={username}")
        if not data:
            return None
        fc = data.get("data", {}).get("user", {}).get("edge_followed_by", {}).get("count")
        return int(fc) if fc is not None else None

    def _fetch_instagram_account(self, username: str) -> list[dict]:
        """抓取 Instagram 账号最近帖子。"""
        uid = self._ig_user_id(username)
        if not uid:
            return []

        data = self._ig_request(f"/api/v1/feed/user/{uid}/?count=12")
        if not data:
            return []

        videos = []
        for item in data.get("items", []):
            cap = item.get("caption") or {}
            caption_text = cap.get("text", "") if isinstance(cap, dict) else ""
            taken_at = item.get("taken_at", 0)
            published = datetime.fromtimestamp(taken_at, tz=timezone.utc) if taken_at else None
            media_type = item.get("media_type", 0)  # 1=image, 2=video, 8=carousel

            v = {
                "id": f"instagram:{item.get('id', '')}",
                "platform": "instagram",
                "title": (caption_text or "")[:200],
                "url": f"https://www.instagram.com/p/{item.get('code', '')}/",
                "views": item.get("play_count", 0) or item.get("view_count", 0) or 0,
                "likes": item.get("like_count", 0) or 0,
                "comments": item.get("comment_count", 0) or 0,
                "shares": 0,
                "duration": 0,
                "tags": re.findall(r"#([\w\-]+)", caption_text),
                "description": caption_text,
                "thumbnail_url": "",
                "published_at": published,
            }
            videos.append(v)

        logger.info("IG %s: %s 条帖子", username, len(videos))
        return videos