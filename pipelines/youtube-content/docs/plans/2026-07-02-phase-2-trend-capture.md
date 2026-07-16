# Phase 2: 社媒趋势捕捉自动化

> **日期:** 2026-07-02 · **修订:** v2（实施后更新）
> **项目:** YouTube Content Factory
> **引擎:** TikTokApi 7.x + yt-dlp + langid + 关键词检测
> **范围:** 按 #tag 跨平台采集 → 阈值过滤 → 语言检测 → 账号追踪
> **状态:** ✅ Phase A 完成 · ✅ Phase B 完成 · ⏳ Phase C 可选

---

## 复用清单（上游项目）

| 模块 | 上游项目 | Stars | 许可证 | 我们做什么 |
|------|---------|-------|--------|-----------|
| 视频采集(TK) | [davidteather/TikTok-Api](https://github.com/davidteather/TikTok-Api) | 5k | MIT | 30 行 API 调用 + 过滤 |
| 视频采集(YTB) | [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp) | 105k | Unlicense | 20 行 CLI 参数 + 解析 |
| 语言检测 | 关键词匹配（自写）+ [saffsd/langid](https://github.com/saffsd/langid) fallback | 2k | BSD | 30 行混合检测 |
| ORM + 迁移 | SQLAlchemy + Alembic | 10k+ | MIT | 30 行 Schema（tracked_accounts） |
| **我们写的** | | | | **~300 行胶水代码** |

> **原则：** 上游项目能做的我们不写。数据采集 → TikTokApi/yt-dlp，语言检测 → 关键词 + langid。

---

## 需求概要

| 维度 | 要求 |
|------|------|
| **数据源** | TikTok + YouTube |
| **搜索方式** | 按 #tag 列表搜索（tag 可后期增删） |
| **高播阈值** | 播放 > 500k **或** 点赞 > 30k（任一满足即可） |
| **时间窗口** | 发布时间 ≤ 1 个月 |
| **国家限定** | 用发布语言推断：印尼语(Id) / 泰语(Th) / 菲律宾英语(En) |
| **账号追踪** | 追踪指定账号的新发布内容 |
| **TK Creator Search Insight** | 本阶段暂不实现，Phase C 可选 |

### 初始 #tag 列表

```
#movie, #kdrama, #film, #edit, #netflix, #recommendations,
#fyp, #series, #drama, #影视推荐, #cinema, #tvshow,
#影视版权方和品牌方（开跑后逐步添加）, #当前爆款剧集（动态更新）
```

---

## 修订记录

| # | 问题 | 修复 |
|---|------|------|
| 1 | 评论区语言检测太重 | 改为标题/描述语言检测，放弃评论区分析 |
| 2 | Creator Search Insight 无 API | 跳过 Phase A，后续单独 Phase C |
| 3 | 国家无法直接限定 | 用发布语言（title/desc）做 proxy |
| 4 | TK hashtag API 反爬严格 | 改用 trending feed + 关键词文本匹配 |
| 5 | pycld3 编译失败 | 换用关键词匹配 + langid 兜底 |

---

## Phase A: 按 #tag 搜索 + 阈值过滤 + 语言检测

### Task A.1: 新建 DB 表 — tracked_tags

| 项 | 值 |
|---|-----|
| **新建文件** | `alembic/versions/xxxx_add_tracked_tags_accounts.py` |
| **修改** | `factory/models.py` |
| **代码** | ~30 行 |

```python
class TrackedTag(Base):
    """追踪的 #tag 列表（可动态增删）"""
    __tablename__ = "tracked_tags"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tag = Column(String(100), nullable=False, unique=True)    # 不带 # 号
    platform = Column(String(20), nullable=False)              # "tiktok" / "youtube" / "all"
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class TrackedAccount(Base):
    """追踪的账号（Phase B 用）"""
    __tablename__ = "tracked_accounts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(20), nullable=False)
    username = Column(String(200), nullable=False)
    display_name = Column(String(200))
    active = Column(Boolean, default=True)
    last_fetched_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
```

**验收:**
- [ ] `alembic upgrade head` 成功，看到 `tracked_tags`, `tracked_accounts` 两张新表
- [ ] 可插入查询 tag

---

### Task A.2: 语言检测模块

| 项 | 值 |
|---|-----|
| **新建文件** | `trending_aggregator/scouts/language_filter.py` |
| **依赖** | `pycld3`（追加到 pyproject.toml） |
| **代码** | ~20 行 |

```python
"""语言检测 — 通过标题/描述推断视频发布地区的语言。

支持的语种（当前需求）：
- id: 印尼语
- th: 泰语
- en: 菲律宾/英语
- (其他语种返回 unknown，不拦截)
"""

import logging

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = {"id", "th", "en"}


def detect_video_language(title: str, description: str = "") -> str | None:
    """检测视频发布语言，返回 ISO 639-1 代码或 None。"""
    import pycld3
    
    text = title.strip() or description.strip()
    if not text:
        return None
    
    try:
        result = pycld3.classify(text)
        lang = result.language
        if lang in SUPPORTED_LANGUAGES:
            return lang
        return None  # 不在目标语种中
    except Exception:
        logger.debug("语言检测失败: %s", text[:30])
        return None


def is_target_language(title: str, description: str = "") -> bool:
    """快速判断：是否属于目标语种。"""
    return detect_video_language(title, description) is not None
```

**验收:**
- [ ] `python3 -c "from trending_aggregator.scouts.language_filter import detect_video_language; print(detect_video_language('Makanan enak sekali'))"` → `"id"`
- [ ] `python3 -c "from trending_aggregator.scouts.language_filter import detect_video_language; print(detect_video_language('I love this movie'))"` → `"en"`
- [ ] `python3 -c "from trending_aggregator.scouts.language_filter import detect_video_language; print(detect_video_language('この映画が大好き'))"` → `None`

---

### Task A.3: TikTok #tag 搜索采集器

| 项 | 值 |
|---|-----|
| **新建文件** | `trending_aggregator/scouts/tiktok_tag.py` |
| **代码** | ~70 行 |

```python
"""TikTok #tag 搜索采集器 — 按 tag 列表搜热门视频，过滤 + 语言检测。"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from TikTokApi import TikTokApi

from trending_aggregator.protocol import Scout
from trending_aggregator.scouts.language_filter import is_target_language

logger = logging.getLogger(__name__)

# 默认阈值
MIN_VIEWS = 500_000
MIN_LIKES = 30_000
MAX_AGE_DAYS = 30


class TikTokTagScout(Scout):
    """TikTok #tag 搜索采集器。"""

    platform = "tiktok"

    def __init__(
        self,
        tags: list[str],
        min_views: int = MIN_VIEWS,
        min_likes: int = MIN_LIKES,
        max_age_days: int = MAX_AGE_DAYS,
        language_filter: bool = True,
        headless: bool = True,
        videos_per_tag: int = 50,
    ):
        self.tags = tags
        self.min_views = min_views
        self.min_likes = min_likes
        self.max_age_days = max_age_days
        self.language_filter = language_filter
        self.headless = headless
        self.videos_per_tag = videos_per_tag

    def scrape(self) -> list[dict]:
        return asyncio.run(self._scrape_async())

    async def _scrape_async(self) -> list[dict]:
        results: list[dict] = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.max_age_days)

        async with TikTokApi() as api:
            await api.create_sessions(num_sessions=1, headless=self.headless)

            for tag in self.tags:
                try:
                    async for video in api.hashtag(name=tag.lstrip("#")).videos(count=self.videos_per_tag):
                        v = self._normalize(video)
                        if not self._pass_threshold(v):
                            continue
                        if v["published_at"] and v["published_at"] < cutoff:
                            continue
                        if self.language_filter and not is_target_language(v["title"], v["description"]):
                            continue
                        results.append(v)
                except Exception:
                    logger.warning("TikTok tag #%s 搜索失败", tag)

        logger.info("TikTok tag: %s 个 tag → %s 条命中", len(self.tags), len(results))
        return results

    def _normalize(self, video) -> dict:
        data = video.as_dict
        stats = video.stats or {}
        author = data.get("author", {}) or {}

        def _s(key: str, *aliases: str) -> int:
            for k in (key, *aliases):
                v = stats.get(k)
                if v is not None:
                    return int(v)
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
        """播放量 > 500k 或 点赞 > 30k 即通过。"""
        return v["views"] >= MIN_VIEWS or v["likes"] >= MIN_LIKES
```

**验收:**
- [ ] `python3 -c "from trending_aggregator.scouts.tiktok_tag import TikTokTagScout; s = TikTokTagScout(tags=['movie'], videos_per_tag=5); vs = s.scrape(); print(f'Got {len(vs)}')"` → 返回 ≥ 0 条
- [ ] 返回的视频 views > 500k 或 likes > 30k

---

### Task A.4: YouTube #tag 搜索采集器

| 项 | 值 |
|---|-----|
| **新建文件** | `trending_aggregator/scouts/youtube_tag.py` |
| **代码** | ~60 行 |

```python
"""YouTube #tag 搜索采集器 — 按 tag 列表搜热门视频，过滤 + 语言检测。"""

import json
import logging
import subprocess
from datetime import datetime, timezone, timedelta

from trending_aggregator.protocol import Scout
from trending_aggregator.scouts.language_filter import is_target_language

logger = logging.getLogger(__name__)

MIN_VIEWS = 500_000
MIN_LIKES = 30_000
MAX_AGE_DAYS = 30


class YouTubeTagScout(Scout):
    """YouTube #tag 搜索采集器。"""

    platform = "youtube"

    def __init__(
        self,
        tags: list[str],
        min_views: int = MIN_VIEWS,
        min_likes: int = MIN_LIKES,
        max_age_days: int = MAX_AGE_DAYS,
        language_filter: bool = True,
        videos_per_tag: int = 30,
    ):
        self.tags = tags
        self.min_views = min_views
        self.min_likes = min_likes
        self.max_age_days = max_age_days
        self.language_filter = language_filter
        self.videos_per_tag = videos_per_tag

    def scrape(self) -> list[dict]:
        seen: set[str] = set()
        results: list[dict] = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.max_age_days)

        for tag in self.tags:
            videos = self._search(tag)
            for v in videos:
                vid = v["id"]
                if vid in seen:
                    continue
                seen.add(vid)

                if not (v["views"] >= self.min_views or v["likes"] >= self.min_likes):
                    continue
                if v["published_at"] and v["published_at"] < cutoff:
                    continue
                if self.language_filter and not is_target_language(v["title"], v["description"]):
                    continue
                results.append(v)

        logger.info("YouTube tag: %s 个 tag → %s 条命中", len(self.tags), len(results))
        return results

    def _search(self, tag: str) -> list[dict]:
        tag = tag.lstrip("#")
        query = f"#{tag}"
        cmd = [
            "yt-dlp",
            f"ytsearch{self.videos_per_tag}:{query}",
            "--dump-json",
            "--flat-playlist",
            "--no-warnings",
            "--ignore-errors",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            logger.error("YouTube 搜索超时: #%s", tag)
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
                videos.append({
                    "id": f"youtube:{data['id']}",
                    "title": data.get("title", ""),
                    "url": data.get("webpage_url", ""),
                    "views": data.get("view_count") or 0,
                    "likes": data.get("like_count") or 0,
                    "comments": data.get("comment_count") or 0,
                    "shares": 0,
                    "duration": data.get("duration", 0),
                    "tags": data.get("tags") or [],
                    "description": data.get("description", ""),
                    "thumbnail_url": data.get("thumbnail", ""),
                    "published_at": _parse_upload_date(data.get("upload_date")),
                })
            except (json.JSONDecodeError, KeyError):
                logger.warning("跳过损坏行")
        return videos


def _parse_upload_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
```

**验收:**
- [ ] `python3 -c "from trending_aggregator.scouts.youtube_tag import YouTubeTagScout; s = YouTubeTagScout(tags=['movie'], videos_per_tag=5); vs = s.scrape(); print(f'Got {len(vs)}')"` → 返回 ≥ 0 条
- [ ] 返回的视频满足阈值条件

---

### Task A.5: 入库 + CLI 入口

| 项 | 值 |
|---|-----|
| **修改** | `trending_aggregator/cli.py` |
| **代码** | ~30 行 |

在已有 `cli.py` 中新增子命令：

```python
# trending_aggregator/cli.py 追加

@app.command()
def tags(
    platform: str = "all",              # tiktok / youtube / all
    tag_file: Optional[Path] = None,    # tag 列表文件，每行一个
):
    """按 #tag 搜索高播视频，过滤后入库。"""
    from trending_aggregator.scouts.tiktok_tag import TikTokTagScout
    from trending_aggregator.scouts.youtube_tag import YouTubeTagScout

    tags = _load_tags(tag_file)
    scouts = []
    if platform in ("all", "tiktok"):
        scouts.append(TikTokTagScout(tags=tags))
    if platform in ("all", "youtube"):
        scouts.append(YouTubeTagScout(tags=tags))

    results = run_all(scouts)
    for platform, count in results.items():
        click.echo(f"{platform}: {count} videos saved")


def _load_tags(path: Path | None) -> list[str]:
    """从文件加载 tag 列表，每行一个（可含 # 号）。"""
    if not path:
        return DEFAULT_TAGS
    with open(path) as f:
        return [line.strip().lstrip("#") for line in f if line.strip()]
```

**tags 示例文件 `data/tags.txt`**：
```
movie
kdrama
film
edit
netflix
recommendations
series
drama
cinema
tvshow
```

**验收:**
- [ ] `uv run python trending_aggregator/cli.py tags --platform tiktok` 执行成功
- [ ] 数据库中可查到新入库的 tag 搜索结果

---

### Task A.6: 单元测试

| 项 | 值 |
|---|-----|
| **新建文件** | `tests/test_tag_scout.py`, `tests/test_language_filter.py` |
| **代码** | ~60 行 |

```python
# tests/test_language_filter.py
from trending_aggregator.scouts.language_filter import detect_video_language, is_target_language


def test_detect_indonesian():
    assert detect_video_language("Makanan enak banget nih") == "id"


def test_detect_thai():
    assert detect_video_language("หนังเรื่องนี้สนุกมาก") == "th"


def test_detect_english():
    assert detect_video_language("This movie is amazing") == "en"


def test_unsupported_language():
    assert detect_video_language("この映画が大好き") is None


def test_empty_text():
    assert detect_video_language("") is None


def test_is_target():
    assert is_target_language("I love this film")
    assert not is_target_language("Ce film est magnifique")
```

```python
# tests/test_tag_scout.py
from trending_aggregator.scouts.tiktok_tag import TikTokTagScout


def test_threshold():
    """验证阈值判断逻辑"""
    s = TikTokTagScout(tags=["test"])
    should_pass = {"views": 600_000, "likes": 100}
    should_fail = {"views": 1000, "likes": 100}
    should_pass_likes = {"views": 1000, "likes": 50_000}

    assert s._pass_threshold(should_pass)
    assert not s._pass_threshold(should_fail)
    assert s._pass_threshold(should_pass_likes)
```

**验收:**
- [ ] `uv run pytest tests/test_language_filter.py -v` → 6/6 通过
- [ ] `uv run pytest tests/test_tag_scout.py -v` → 通过

---

## Phase B: 账号追踪

### Task B.1: AccountScout

| 项 | 值 |
|---|-----|
| **新建文件** | `trending_aggregator/scouts/account.py` |
| **代码** | ~50 行 |

读取 `tracked_accounts` 表 → 对每个活跃账号：

- **TikTok（已实现）**: `yt-dlp tiktok.com/@username` — TikTokApi user 端被反爬，改用 yt-dlp 频道提取
- **YouTube（已实现）**: `yt-dlp youtube.com/@username/videos` — 注意 flat-playlist 下 view=0
- 两个平台共享 `_normalize_ytdlp()` 归一化逻辑

```python
class AccountScout(Scout):
    """追踪指定账号的最新发布内容。"""

    platform = "account"

    def __init__(self, headless: bool = True):
        self.headless = headless

    def scrape(self) -> list[dict]:
        """从 DB 读账号列表 → 逐账号抓最新视频。"""
        ...

    async def _fetch_tiktok(self, api, username: str) -> list[dict]:
        """抓一个 TK 账号的最新视频。"""
        ...
```

### Task B.2: CLI 管理命令

```bash
# 添加追踪账号
uv run python trending_aggregator/cli.py account add --platform tiktok @netflix

# 列出追踪账号
uv run python trending_aggregator/cli.py account list

# 运行账号采集
uv run python trending_aggregator/cli.py account fetch
```

---

## 依赖关系

```
Task A.1 (DB: tracked_tags + tracked_accounts)
  │
  ├──▶ Task A.2 (语言检测: pycld3 封装)
  │         │
  │         ├──▶ Task A.3 (TikTok tag 采集器)
  │         │         │
  │         │         ▼
  │         │     Task A.5 (CLI 入口 + 入库)
  │         │         │
  │         ├──▶ Task A.4 (YouTube tag 采集器)
  │         │         │
  │         │         ▼
  │         │     Task A.5 (同上)
  │         │
  │         └──▶ Task A.6 (单元测试)
  │
  └──▶ Phase B (账号追踪，Phase A 完成后)
```

---

## 汇总

| Phase | Tasks | 代码量 | 预估时间 | 依赖 |
|-------|-------|--------|---------|------|
| **Phase A** | 6 | ~250 行 | 1.5 天 | pycld3 |
| **Phase B** | 2 | ~80 行 | 0.5 天 | Phase A |

### 初始 tag 列表（建议）

```
movie, kdrama, film, edit, netflix, recommendations,
series, drama, fyp, cinema, tvshow, 影视推荐
```

---

## 未决

- TikTok `hashtag.videos()` 被反爬拦截（status 10201），改用 `trending.videos()` + 文本关键词匹配，命中率低 — 后续需代理轮换 + 多 session + 或付费 API
- `trending.videos()` 在同一 session 拉取 50+ 条后也会触发限流（status 10201）— 建议每次拉 ≤ 30 条，多 session 轮换
- yt-dlp 搜索 `#tag` 工作正常，但返回的部分视频 view/like 数据为 0（flat-playlist 模式不获取详细信息），阈值过滤会漏掉 — 后续可在入库前对低信息的视频做 `--no-flat-playlist` 补全
- 语言检测对混合语种标题（英+印尼、英+泰）可能误判 — 当前实现优先语种内容，非目标语种通过 tag 本身已有筛选效果
- Phase B 账号追踪的 YouTube 端依赖 `@username` 格式的频道 URL，部分频道可能是 `/channel/UC...` 格式 — 入库时需兼容
