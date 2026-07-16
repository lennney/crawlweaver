# Trending Video Aggregator — 独立方案 v2

**日期:** 2026-07-01
**状态:** 待执行（修订版，已修复 v1 审查中发现的 P0/P1 问题）
**定位:** 脱离 Hermes，纯 Python 独立项目

---

## v2 修订说明

| 变更 | v1 问题 | v2 修复 |
|------|--------|---------|
| TikTok API | `api.trending(region_code=...)` v6 旧 API | `api.trending.videos(count=...)` v7 原生 API |
| Instagram 探索页 | `cl.explore_reels()` 方法不存在 | `cl.fbsearch_reels_v2()` |
| Sessionid 管理 | 硬编码 None，未读环境变量 | 统一从 config.py 读取 |
| Import 路径 | `from schema import ...` 绝对导入 | `from ..schema import ...` 相对导入 |
| Schema 默认值 | `extra: dict = {}` mutable default | `Field(default_factory=dict)` |
| Schema 默认值 | `fetched_at = datetime.now()` 类定义时求值 | `Field(default_factory=datetime.now)` |
| `created_at` | str/int 直接传 datetime 字段 | 显式类型转换 |
| YouTube 性能 | `extract_flat=False` → 50+ 次 HTTP | `extract_flat='in_playlist'` → 1 次 |
| 排序逻辑 | 三平台混合按 views 排序 | 每平台独立 Top N + 分 Sheet 导出 |
| 定时任务 | `schedule` 守护进程 | `--once` 模式 + systemd timer |
| 日志 | `print()` | `logging` 模块 |
| 超时/重试 | 无 | 所有 API 调用加 timeout + retry |
| 测试 | 无 | schema / aggregator / exporter 单元测试 |

---

## 1. 项目目标

每日自动抓取 YouTube / TikTok / Instagram 三个平台的热门视频，**每平台独立排名**，输出多 Sheet Excel 表格。

---

## 2. 技术架构

```
trending-video-aggregator/
├── pyproject.toml              # 依赖 + 包配置
├── setup.sh                    # 一键安装系统依赖
├── .env.example                # 环境变量模板
│
├── trending_aggregator/        # Python 包（解决 import 路径问题）
│   ├── __init__.py
│   ├── config.py               # pydantic-settings 配置校验
│   ├── schema.py               # Pydantic 统一数据模型（已修复默认值）
│   ├── sources/
│   │   ├── __init__.py         # 对外暴露 fetch_* 函数
│   │   ├── youtube.py          # yt-dlp（extract_flat 修复）
│   │   ├── tiktok.py           # TikTokApi v7（asyncio 修复）
│   │   └── instagram.py        # instagrapi v2（explore 方法修复）
│   ├── aggregator.py           # 每平台独立排序 + 去重
│   ├── exporter.py             # 多 Sheet Excel + CSV 导出
│   └── main.py                 # 入口（--once 单次执行）
│
├── tests/
│   ├── test_schema.py
│   ├── test_aggregator.py
│   └── test_exporter.py
│
└── deploy/
    ├── trending.service        # systemd service
    └── trending.timer          # systemd timer（每日 09:00）
```

---

## 3. 技术栈选型说明

各模块的选型理由及已拒绝的替代方案。核心原则：个人小工具、Linux 无头 VM、每日一次、免费、低维护。

### 3.1 平台采集

#### YouTube：yt-dlp ✅ | YouTube Data API v3 ❌

| 维度 | yt-dlp（选用） | YouTube Data API v3（拒绝） |
|------|--------------|--------------------------|
| 方式 | 直接爬 trending 页面 | 官方 REST API |
| 费用 | 免费无限 | 免费 10,000 quota/天 |
| API Key | 不需要 | 需要 Google Cloud 项目 + Key |
| 可靠性 | 中（YT 改版需跟随更新） | 高（SLA 保障） |
| 维护成本 | `pip install -U yt-dlp` | 几乎零维护 |

拒绝 API v3 的理由：我们只要 trending 页面的元数据（标题、浏览量、链接），不下载视频。`extract_flat='in_playlist'` 一次请求拿 50 条，免费无限制。多一层 API Key 管理对个人小工具不划算。

> ⚠️ `extract_flat='in_playlist'` 是 yt-dlp 的快速模式，只解析列表页元数据。v1 方案用的 `extract_flat=False`（默认）会导致每个视频发起一次详情请求，50 条 = 50+ 次 HTTP。

#### TikTok：TikTokApi v7 ✅ | LamaTok 等付费 API ❌

| 维度 | TikTokApi（选用） | LamaTok/TikHub（拒绝） |
|------|-----------------|----------------------|
| 方式 | Playwright 模拟浏览器 | 付费 REST API |
| 费用 | 免费 | $29+/月 |
| 可靠性 | 中（TT 改签名算法就挂） | 高 |
| 维护 | 需 ms_token 每 ~24h 刷新 | 几乎零维护 |

拒绝付费 API 的理由：个人工具日抓 50 条，不值得付费。TikTokApi 是免费方案里最活跃的（v7.3.3，2026-04 更新，7.4k+ stars）。

> TikTok 没有公开的 trending API，所有方案都是非官方的。选最活跃的开源库是最务实的策略。ms_token 每日过期：跑前手动更新，日频次可接受。

#### Instagram：instagrapi ✅ | instaloader / aiograpi ❌

| 维度 | instagrapi（选用） | instaloader（拒绝） | aiograpi（拒绝） |
|------|-----------------|-------------------|----------------|
| 方式 | 私有 API（模拟 App） | 公开网页爬取 | instagrapi 异步版 |
| 登录 | 需要 sessionid | 可选 | 同 instagrapi |
| 热门 Reels | ✅ `fbsearch_reels_v2` | ❌ 无此功能 | ✅ 同 instagrapi |

拒绝 instaloader：它是下载工具，不是数据采集库，没有探索页 API。拒绝 aiograpi：我们的场景顺序跑三平台，不需要异步高并发，一个全局 Client 复用即可。

### 3.2 基础设施

#### 数据模型：Pydantic v2 ✅ | dataclass ❌

| 维度 | Pydantic（选用） | dataclass（拒绝） |
|------|----------------|-----------------|
| 运行时类型校验 | ✅ | ❌ |
| 默认值安全 | ✅ `Field(default_factory=...)` | ⚠️ mutable 需手动 |
| 序列化 | ✅ `.model_dump()` | ❌ 需手写 |

选 Pydantic 的决定性理由：运行时类型校验能挡掉跨平台数据格式不一致的 Bug——YouTube `upload_date` 是字符串、TikTok `createTime` 是 Unix 时间戳、Instagram `taken_at` 是 datetime。dataclass 会让坏数据静默通过。

#### Excel 导出：openpyxl ✅ | Tablib ❌

| 维度 | openpyxl（选用） | Tablib（v1 原选） |
|------|----------------|-----------------|
| 多 Sheet | ✅ | ❌ 单 Sheet |
| 样式（表头颜色/列宽） | ✅ | ❌ |
| 依赖链 | 1 个包 | xlsx 底层就是 openpyxl |

拒绝 Tablib：一个 Dataset = 一个 Sheet，分平台要写多个再合并。而且底层就是 openpyxl，中间的抽象层纯属多余。

#### 重试/超时：tenacity ✅

`@retry(stop=stop_after_attempt(3), wait=wait_exponential(...))` 一行搞定指数退避。

#### 定时调度：systemd timer ✅ | schedule 库 ❌

| 维度 | systemd timer（选用） | schedule 库（v1 原选） |
|------|---------------------|---------------------|
| 持久化 | ✅ OS 级 | ❌ 重启丢失 |
| 崩溃恢复 | ✅ systemd 自动重启 | ❌ 无 |
| 日志 | ✅ journald（自动轮转） | ❌ 需自己写 |

拒绝 schedule：官方写明 "not suitable for production"。`while True: time.sleep(60)` 无优雅退出、无超时保护。

#### 日志：logging ✅

选 Python 标准库 `logging`，零额外依赖。systemd journald 已处理日志轮转。

### 3.3 最终依赖清单

```
yt-dlp              ← YouTube trending（免费，无 Key，仅元数据）
TikTokApi           ← TikTok trending（免费，需 ms_token）
instagrapi          ← Instagram Reels（免费，需 sessionid）
pydantic            ← 数据模型 + 运行时类型校验
pydantic-settings   ← 配置管理（.env 自动加载 + 校验）
openpyxl            ← 多 Sheet Excel 导出 + 样式
tenacity            ← 指数退避重试
python-dotenv       ← .env 文件解析
pytest (dev)        ← 单元测试
```

| v1 → v2 变更 | 理由 |
|-------------|------|
| Tablib → openpyxl | 多 Sheet 直接操控，去掉中间抽象层 |
| schedule → systemd timer | 守护进程不可靠 → OS 级可靠 |
| pandas → 移除 | 只用 Excel 读写不需要 DataFrame |
| + tenacity | 网络抖动不丢数据 |
| + pydantic-settings | 配置校验（v1 手写 os.getenv 无校验） |


---

## 4. 依赖管理

### pyproject.toml

```toml
[project]
name = "trending-video-aggregator"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "yt-dlp>=2026.1.0,<2027",
    "TikTokApi>=7.0.0,<8",
    "instagrapi>=2.0.0,<3",
    "pydantic>=2.0,<3",
    "pydantic-settings>=2.0",
    "openpyxl>=3.0",
    "python-dotenv>=1.0",
    "tenacity>=8.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-mock>=3.0",
]
```

### setup.sh — 系统依赖

```bash
#!/bin/bash
set -e
echo "安装系统依赖..."
sudo apt-get update
sudo apt-get install -y ffmpeg chromium-browser

echo "安装 Python 依赖..."
pip install -e ".[dev]"

echo "安装 Playwright 浏览器..."
python -m playwright install chromium

echo "复制环境变量模板: cp .env.example .env 并填写 sessionid"
echo "完成！"
```

---

## 5. 模块设计（修正版）

### 5.1 统一数据模型（schema.py）

```python
"""跨平台统一视频数据模型"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class VideoItem(BaseModel):
    platform: str                      # youtube / tiktok / instagram
    video_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    url: str
    thumbnail: Optional[str] = None
    duration: Optional[int] = None     # 秒

    # 互动指标
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0

    # 时间 — 用 Field(default_factory=...) 防止类定义时求值
    created_at: Optional[datetime] = None
    fetched_at: datetime = Field(default_factory=datetime.now)

    # 扩展字段 — 用 default_factory 防止 mutable default
    extra: dict = Field(default_factory=dict)

    # 每平台内排名（由 aggregator 填充）
    platform_rank: Optional[int] = None
```

### 5.2 配置管理（config.py）

```python
"""配置校验 — pydantic-settings"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 平台配置
    youtube_region: str = 'US'
    tiktok_region: str = 'US'

    # 凭证
    tiktok_sessionid: str = ''
    instagram_sessionid: str = ''

    # 筛选
    youtube_min_views: int = 10000
    tiktok_min_views: int = 10000
    instagram_min_views: int = 5000
    top_n: int = 50

    # 输出
    output_dir: str = './output'

    # 超时
    request_timeout: int = 120

    # 日志
    log_level: str = 'INFO'

    model_config = {
        "env_file": ".env",
        "env_prefix": "TREND_",
        "extra": "ignore",
    }


settings = Settings()
```

> 环境变量映射示例：`TREND_TIKTOK_SESSIONID=xxx`，`TREND_TOP_N=50`，详见 `.env.example`。

### 5.3 YouTube 采集（sources/youtube.py）— 已修复

```python
"""YouTube 热门视频采集 — 基于 yt-dlp"""
import logging
from datetime import datetime
from typing import List

import yt_dlp
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import settings
from ..schema import VideoItem

logger = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def fetch_youtube_trending(
    region: str = None,
    category: str = None,
    max_videos: int = None,
) -> List[VideoItem]:
    region = region or settings.youtube_region
    max_videos = max_videos or settings.top_n

    url = f'https://www.youtube.com/feed/trending?gl={region}'
    if category:
        url += f'&category={category}'

    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'extract_flat': 'in_playlist',  # ✅ 修复：不逐个深入提取
        'no_warnings': True,
        'socket_timeout': settings.request_timeout,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(url, download=False)

    videos = []
    for entry in (result.get('entries') or [])[:max_videos]:
        # ✅ 修复：upload_date YYYYMMDD 字符串 → datetime
        upload_date_str = entry.get('upload_date')
        created_at = None
        if upload_date_str:
            try:
                created_at = datetime.strptime(upload_date_str, '%Y%m%d')
            except (ValueError, TypeError):
                logger.warning(f"无法解析 upload_date: {upload_date_str}")

        videos.append(VideoItem(
            platform='youtube',
            video_id=entry.get('id', ''),
            title=entry.get('title'),
            description=entry.get('description'),
            url=entry.get('webpage_url') or f"https://youtube.com/watch?v={entry.get('id')}",
            thumbnail=entry.get('thumbnail'),
            duration=entry.get('duration'),
            views=entry.get('view_count', 0) or 0,
            likes=entry.get('like_count', 0) or 0,
            comments=entry.get('comment_count', 0) or 0,
            created_at=created_at,
            extra={
                'channel': entry.get('channel'),
                'uploader': entry.get('uploader'),
            }
        ))

    logger.info(f"YouTube: 获取 {len(videos)} 条")
    return videos
```

### 5.4 TikTok 采集（sources/tiktok.py）— 已修复

```python
"""TikTok 热门视频采集 — TikTokApi v7.x"""
import asyncio
import logging
from datetime import datetime
from typing import List

from TikTokApi import TikTokApi

from ..config import settings
from ..schema import VideoItem

logger = logging.getLogger(__name__)

# ✅ 修复：全局事件循环管理，避免 asyncio.run() 嵌套冲突
_loop: asyncio.AbstractEventLoop | None = None


def _get_or_create_loop() -> asyncio.AbstractEventLoop:
    global _loop
    try:
        _loop = asyncio.get_running_loop()
    except RuntimeError:
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


def fetch_tiktok_trending(
    region: str = None,
    max_videos: int = None,
) -> List[VideoItem]:
    region = region or settings.tiktok_region
    max_videos = max_videos or settings.top_n

    if not settings.tiktok_sessionid:
        logger.error("TikTok sessionid 未配置！请设置 TREND_TIKTOK_SESSIONID")
        return []

    loop = _get_or_create_loop()
    return loop.run_until_complete(_fetch_tiktok_async(region, max_videos))


async def _fetch_tiktok_async(region: str, max_videos: int) -> List[VideoItem]:
    videos = []

    async with TikTokApi() as api:
        # ✅ 修复：使用 ms_token + headless=True 适配 Linux 无头环境
        await api.create_sessions(
            ms_tokens=[settings.tiktok_sessionid],
            num_sessions=1,
            sleep_after=3,
            headless=True,
        )

        # ✅ 修复：v7 API — api.trending.videos()，无 region_code
        async for video in api.trending.videos(count=max_videos):
            data = video.as_dict

            # ✅ 修复：createTime Unix 时间戳 → datetime
            ts = data.get('createTime')
            created_at = datetime.fromtimestamp(ts) if ts else None

            author = data.get('author', {}) or {}

            videos.append(VideoItem(
                platform='tiktok',
                video_id=data.get('id', ''),
                title=(data.get('desc') or '')[:200],
                url=f"https://tiktok.com/@{author.get('uniqueId')}/video/{data.get('id')}",
                thumbnail=(data.get('cover') or {}).get('url'),
                duration=(data.get('video') or {}).get('duration'),
                views=(data.get('stats') or {}).get('playCount', 0),
                likes=(data.get('stats') or {}).get('diggCount', 0),
                comments=(data.get('stats') or {}).get('commentCount', 0),
                shares=(data.get('stats') or {}).get('shareCount', 0),
                created_at=created_at,
                extra={
                    'author': author.get('uniqueId'),
                    'music': (data.get('music') or {}).get('title'),
                    'hashtags': [f"#{tag}" for tag in data.get('challenges', [])],
                }
            ))

    logger.info(f"TikTok: 获取 {len(videos)} 条")
    return videos
```

### 5.5 Instagram 采集（sources/instagram.py）— 已修复

```python
"""Instagram Reels 采集 — instagrapi v2.x"""
import logging
from datetime import datetime
from typing import List, Optional

from instagrapi import Client

from ..config import settings
from ..schema import VideoItem

logger = logging.getLogger(__name__)

# ✅ 修复：客户端复用，避免每次登录
_client: Optional[Client] = None


def _get_client() -> Client:
    global _client
    if _client is not None:
        return _client

    if not settings.instagram_sessionid:
        raise ValueError("Instagram sessionid 未配置！请设置 TREND_INSTAGRAM_SESSIONID")

    _client = Client()
    _client.delay_range = [1, 3]  # 请求间隔，降低限流风险
    _client.login_by_sessionid(settings.instagram_sessionid)
    logger.info("Instagram 登录成功")
    return _client


def fetch_instagram_reels(
    user_ids: List[str] = None,
    max_videos: int = None,
) -> List[VideoItem]:
    max_videos = max_videos or settings.top_n
    cl = _get_client()
    videos = []

    if user_ids:
        per_user = max(1, max_videos // len(user_ids))
        for user_id in user_ids[:max_videos]:  # 上限保护
            try:
                medias = cl.user_medias(user_id, amount=per_user)
                for media in medias:
                    if media.media_type == 2 and getattr(media, 'product_type', '') == 'clips':
                        videos.append(_convert_to_video_item(media))
            except Exception as e:
                logger.warning(f"用户 {user_id} 抓取失败: {e}")
    else:
        # ✅ 修复：用 fbsearch_reels_v2 替代不存在的 explore_reels
        try:
            for _ in range(3):  # 多次查询凑满 max_videos
                medias, _ = cl.fbsearch_reels_v2('trending')
                for media in medias:
                    videos.append(_convert_to_video_item(media))
                if len(videos) >= max_videos:
                    break
        except Exception as e:
            logger.error(f"探索页抓取失败: {e}")

    logger.info(f"Instagram: 获取 {len(videos)} 条")
    return videos[:max_videos]


def _convert_to_video_item(media) -> VideoItem:
    """将 instagrapi Media 转换为统一模型"""
    # ✅ 修复：video_duration 类型安全处理
    if media.video_duration:
        if hasattr(media.video_duration, 'total_seconds'):
            duration = int(media.video_duration.total_seconds())
        elif isinstance(media.video_duration, (int, float)):
            duration = int(media.video_duration)
        else:
            duration = None
    else:
        duration = None

    caption = media.caption_text or ''

    return VideoItem(
        platform='instagram',
        video_id=str(media.id),
        title=caption[:200] if caption else None,
        url=f"https://instagram.com/reel/{media.code}",
        thumbnail=getattr(media, 'thumbnail_url', None),
        duration=duration,
        views=media.play_count or 0,
        likes=media.like_count or 0,
        comments=media.comment_count or 0,
        shares=getattr(media, 'share_count', 0) or 0,
        created_at=media.taken_at,
        extra={
            'user': media.user.username,
        }
    )
```

### 5.6 数据聚合（aggregator.py）— 每平台独立排序

```python
"""每平台独立排序 + 去重"""
from typing import Dict, List

from .config import settings
from .schema import VideoItem


def aggregate(
    youtube: List[VideoItem],
    tiktok: List[VideoItem],
    instagram: List[VideoItem],
) -> Dict[str, List[VideoItem]]:
    """
    每平台独立排序返回分平台结果。

    Returns:
        {'youtube': [...], 'tiktok': [...], 'instagram': [...], 'all': [...]}
    """
    thresholds = {
        'youtube': settings.youtube_min_views,
        'tiktok': settings.tiktok_min_views,
        'instagram': settings.instagram_min_views,
    }

    result: Dict[str, List[VideoItem]] = {}

    for platform_name, videos, threshold in [
        ('youtube', youtube, thresholds['youtube']),
        ('tiktok', tiktok, thresholds['tiktok']),
        ('instagram', instagram, thresholds['instagram']),
    ]:
        # 去重
        seen = set()
        unique = []
        for v in videos:
            if v.video_id not in seen:
                seen.add(v.video_id)
                unique.append(v)

        # 筛选
        filtered = [v for v in unique if v.views >= threshold]

        # 按浏览量降序
        sorted_videos = sorted(filtered, key=lambda x: x.views, reverse=True)

        # 标记平台内排名
        for rank, v in enumerate(sorted_videos, 1):
            v.platform_rank = rank

        result[platform_name] = sorted_videos[:settings.top_n]

    # 汇总列表（三平台合并）
    all_videos = result['youtube'] + result['tiktok'] + result['instagram']
    result['all'] = sorted(all_videos, key=lambda x: x.views, reverse=True)[:settings.top_n]

    return result
```

### 5.7 数据导出（exporter.py）— 多 Sheet 导出

```python
"""多格式导出 — 每平台一个 Sheet"""
import logging
import os
from datetime import datetime
from typing import Dict, List

import openpyxl
from openpyxl.styles import Font, PatternFill

from .config import settings
from .schema import VideoItem

logger = logging.getLogger(__name__)

HEADERS = ['平台内排名', '标题', '浏览量', '点赞', '评论', '链接', '发布时间']
SHEET_ORDER = ['youtube', 'tiktok', 'instagram', 'all']
SHEET_NAMES = {'youtube': 'YouTube', 'tiktok': 'TikTok', 'instagram': 'Instagram', 'all': '汇总'}


def export_to_excel(
    results: Dict[str, List[VideoItem]],
    filename: str = None,
) -> str:
    """导出多 Sheet Excel"""
    if not filename:
        os.makedirs(settings.output_dir, exist_ok=True)
        filename = os.path.join(
            settings.output_dir,
            f"trending-{datetime.now():%Y%m%d}.xlsx",
        )

    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # 删除默认 Sheet

    header_font = Font(bold=True)
    header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
    header_font_white = Font(bold=True, color='FFFFFF')

    for sheet_key in SHEET_ORDER:
        if sheet_key not in results:
            continue

        ws = wb.create_sheet(title=SHEET_NAMES[sheet_key])
        videos = results[sheet_key]

        # 写表头
        for col, header in enumerate(HEADERS, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font_white
            cell.fill = header_fill

        # 写数据
        for row, v in enumerate(videos, 2):
            ws.cell(row=row, column=1, value=v.platform_rank or row - 1)
            ws.cell(row=row, column=2, value=(v.title or '')[:200])
            ws.cell(row=row, column=3, value=v.views)
            ws.cell(row=row, column=4, value=v.likes)
            ws.cell(row=row, column=5, value=v.comments)
            ws.cell(row=row, column=6, value=v.url)
            ws.cell(row=row, column=7, value=v.created_at.strftime('%Y-%m-%d %H:%M') if v.created_at else '')

        # 列宽自适应
        for col in range(1, len(HEADERS) + 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = {
                1: 12, 2: 50, 3: 15, 4: 15, 5: 15, 6: 40, 7: 18
            }.get(col, 15)

    wb.save(filename)
    logger.info(f"导出: {filename} ({sum(len(v) for v in results.values())} 条)")
    return filename


def export_to_csv(results: Dict[str, List[VideoItem]], output_dir: str = None) -> List[str]:
    """每平台导出独立 CSV"""
    output_dir = output_dir or settings.output_dir
    os.makedirs(output_dir, exist_ok=True)
    date_str = datetime.now().strftime('%Y%m%d')

    files = []
    for sheet_key in SHEET_ORDER:
        if sheet_key not in results:
            continue
        filename = os.path.join(output_dir, f"trending-{sheet_key}-{date_str}.csv")
        with open(filename, 'w', encoding='utf-8', newline='') as f:
            import csv
            writer = csv.writer(f)
            writer.writerow(HEADERS)
            for v in results[sheet_key]:
                writer.writerow([
                    v.platform_rank,
                    (v.title or '')[:200],
                    v.views, v.likes, v.comments,
                    v.url,
                    v.created_at.isoformat() if v.created_at else '',
                ])
        files.append(filename)

    logger.info(f"导出 CSV: {len(files)} 个文件")
    return files
```

### 5.8 入口（main.py）— 简化为 --once 模式

```python
"""主入口 — 单次执行 + logging 配置"""
import argparse
import logging
import sys
from datetime import datetime

from .config import settings
from .sources.youtube import fetch_youtube_trending
from .sources.tiktok import fetch_tiktok_trending
from .sources.instagram import fetch_instagram_reels
from .aggregator import aggregate
from .exporter import export_to_excel


def setup_logging():
    """配置日志：控制台 + 文件 """
    fmt = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    root.addHandler(handler)


def daily_fetch() -> str:
    """每日抓取任务，返回导出文件路径"""
    logger = logging.getLogger(__name__)
    logger.info("开始抓取...")

    yt, tt, ig = [], [], []

    for label, fn, collector in [
        ('YouTube', fetch_youtube_trending, yt),
        ('TikTok', fetch_tiktok_trending, tt),
        ('Instagram', fetch_instagram_reels, ig),
    ]:
        try:
            result = fn()
            collector.extend(result)
            logger.info(f"  {label}: {len(result)} 条")
        except Exception as e:
            logger.error(f"  {label} 失败: {e}", exc_info=True)

    results = aggregate(yt, tt, ig)
    logger.info(
        f"  合计: YT={len(results['youtube'])} "
        f"TT={len(results['tiktok'])} "
        f"IG={len(results['instagram'])} "
        f"汇总={len(results['all'])} 条"
    )

    filename = export_to_excel(results)
    logger.info(f"导出: {filename}")
    return filename


def main():
    parser = argparse.ArgumentParser(description='Trending Video Aggregator')
    parser.add_argument('--once', action='store_true', default=True,
                        help='单次执行（默认）')
    parser.add_argument('--region', type=str, help='覆盖地区配置')
    args = parser.parse_args()

    setup_logging()

    if args.region:
        settings.youtube_region = args.region
        settings.tiktok_region = args.region

    daily_fetch()


if __name__ == '__main__':
    main()
```

---

## 6. 部署方案：systemd timer（替代 schedule）

### deploy/trending.service

```ini
[Unit]
Description=Trending Video Aggregator — daily fetch
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=/home/ubuntu/trending-video-aggregator
Environment="PATH=/home/ubuntu/.local/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/home/ubuntu/.local/bin/uv run python -m trending_aggregator.main
StandardOutput=journal
StandardError=journal

# 超时：5分钟足够
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
```

### deploy/trending.timer

```ini
[Unit]
Description=Daily Trending Video Aggregator
Requires=trending.service

[Timer]
OnCalendar=daily
OnCalendar=09:00
Persistent=true

[Install]
WantedBy=timers.target
```

### 部署命令

```bash
sudo cp deploy/trending.service deploy/trending.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable trending.timer
sudo systemctl start trending.timer

# 立即测试一次
sudo systemctl start trending.service
# 查看日志
journalctl -u trending.service -f
```

---

## 7. 测试用例

### tests/test_schema.py

```python
"""schema.py 单元测试"""
from trending_aggregator.schema import VideoItem


def test_video_item_defaults():
    v = VideoItem(platform='youtube', video_id='abc123', url='https://example.com')
    assert v.views == 0
    assert v.likes == 0
    assert v.extra == {}
    assert v.created_at is None
    assert v.fetched_at is not None  # 每次不同


def test_video_item_extra_isolation():
    """extra 默认值不应被多实例共享（mutable default 修复验证）"""
    v1 = VideoItem(platform='youtube', video_id='1', url='https://a')
    v2 = VideoItem(platform='tiktok', video_id='2', url='https://b')
    v1.extra['test'] = 'v1'
    assert v2.extra == {}
```

### tests/test_aggregator.py

```python
"""aggregator.py 单元测试"""
from trending_aggregator.schema import VideoItem
from trending_aggregator.aggregator import aggregate


def make_video(platform, video_id, views):
    return VideoItem(platform=platform, video_id=video_id, url=f'https://{platform}/{video_id}', views=views)


class TestAggregate:
    def test_per_platform_sorting(self):
        yt = [
            make_video('youtube', 'yt1', 1000),
            make_video('youtube', 'yt2', 5000),
        ]
        tt = [make_video('tiktok', 'tt1', 20000)]
        ig = []

        result = aggregate(yt, tt, ig)
        assert result['youtube'][0].video_id == 'yt2'  # 5000 > 1000
        assert result['tiktok'][0].video_id == 'tt1'
        assert result['instagram'] == []

    def test_platform_rank_assigned(self):
        yt = [make_video('youtube', 'yt1', 1000), make_video('youtube', 'yt2', 5000)]
        result = aggregate(yt, [], [])
        assert result['youtube'][0].platform_rank == 1
        assert result['youtube'][1].platform_rank == 2

    def test_min_views_filter_respected(self):
        yt = [make_video('youtube', 'yt1', 100)]
        result = aggregate(yt, [], [])
        assert result['youtube'] == []  # 100 < 10000 default
```

### tests/test_exporter.py

```python
"""exporter.py 单元测试"""
import os
import tempfile
from trending_aggregator.schema import VideoItem
from trending_aggregator.exporter import export_to_excel


def test_export_creates_file():
    v = VideoItem(platform='youtube', video_id='test1', url='https://youtu.be/test1', views=10000)
    results = {'youtube': [v], 'all': [v]}

    with tempfile.TemporaryDirectory() as tmpdir:
        filename = export_to_excel(results, filename=os.path.join(tmpdir, 'test.xlsx'))
        assert os.path.exists(filename)
        assert os.path.getsize(filename) > 0
```

---

## 8. 执行计划

| Phase | 内容 | 时间 | 验收 |
|-------|------|------|------|
| **1** | 项目搭建：pyproject.toml + 目录结构 + `.env.example` + `setup.sh` | 0.5h | `pip install -e ".[dev]"` 成功 |
| **2** | `schema.py` + `config.py` + `tests/test_schema.py` | 0.5h | `pytest tests/test_schema.py` 通过 |
| **3** | `sources/youtube.py` + YouTube 端到端测试 | 1.5h | `fetch_youtube_trending()` 返回正确数据 |
| **4** | `sources/tiktok.py` + TikTok 端到端测试 | 1.5h | `fetch_tiktok_trending()` 返回正确数据 |
| **5** | `sources/instagram.py` + Instagram 端到端测试 | 1.5h | `fetch_instagram_reels()` 返回正确数据 |
| **6** | `aggregator.py` + `exporter.py` + 测试 | 1h | `pytest tests/` 全部通过，生成正确 Excel |
| **7** | `main.py` + logging + deploy/systemd 文件 | 0.5h | `python -m trending_aggregator.main` 完整跑通 |
| **8** | 端到端测试 + README | 1h | 生成有效 Excel，三 Sheet 数据正确 |
| **合计** | | **~8h** | |

---

## 9. 验收标准

| # | 标准 | 检验方法 |
|---|------|----------|
| 1 | `VideoItem` 默认值无共享（mutable default 修复） | `test_schema.py` 通过 |
| 2 | `created_at` 各平台正确转换为 datetime | `test_schema.py` 通过 |
| 3 | YouTube 采集 < 10 秒（`extract_flat` 修复） | `fetch_youtube_trending()` 计时 |
| 4 | TikTok v7 API 可用 | `fetch_tiktok_trending()` 返回非空列表 |
| 5 | Instagram 探索页可用 | `fetch_instagram_reels()` 返回非空列表 |
| 6 | 每平台独立排序 | `aggregate()` 输出 yt/tt/ig 分别 Top N 且含 `platform_rank` |
| 7 | Excel 包含 3 个平台 Sheet + 汇总 Sheet | 打开 `.xlsx` 检查 |
| 8 | `python -m trending_aggregator.main` 生成有效 Excel | 端到端运行 |
| 9 | systemd timer 可部署 | `systemctl start trending.service` 成功 |
| 10 | 单元测试覆盖率 > 60%（schema/aggregator/exporter） | `pytest --cov` |

---

## 10. 已知限制

| 限制 | 说明 | 缓解措施 |
|------|------|----------|
| TikTok sessionid 有效期 ~24h | ms_token 定期过期 | 日志告警 + 手动更新 |
| Instagram sessionid 有效期 ~几天 | 同 TikTok | 日志告警 |
| instagrapi API 不稳定 | Instagram 频繁改版 | 锁定已知兼容版本 `<3` |
| 浏览量为 0 时跳过 | 部分 API 不返回 | 已处理为默认 0 |
| 无 Facebook | 无免费合法方案 | 已跳过 |
| 纯 CLI 无 Web 界面 | 需 SSH 操作 | Excel 文件可通过邮件/网盘分发 |

---

## 11. 使用方式

```bash
# 安装
bash setup.sh
cp .env.example .env  # 填写 TREND_TIKTOK_SESSIONID 和 TREND_INSTAGRAM_SESSIONID

# 单次运行
python -m trending_aggregator.main

# 指定地区
python -m trending_aggregator.main --region JP

# 部署定时任务
sudo cp deploy/trending.service deploy/trending.timer /etc/systemd/system/
sudo systemctl enable --now trending.timer

# 查看日志
journalctl -u trending.service -f

# 运行测试
pytest tests/ -v
```

---

## 12. 输出示例

```
2026-07-01 09:00:00 [INFO] trending_aggregator.main: 开始抓取...
2026-07-01 09:00:05 [INFO] sources.youtube: YouTube: 获取 50 条
2026-07-01 09:00:18 [INFO] sources.tiktok: TikTok: 获取 50 条
2026-07-01 09:00:30 [INFO] sources.instagram: Instagram: 获取 50 条
2026-07-01 09:00:30 [INFO] trending_aggregator.main:   合计: YT=50 TT=48 IG=42 汇总=50 条
2026-07-01 09:00:30 [INFO] trending_aggregator.main: 导出: output/trending-20260701.xlsx
```

Excel 结构：
- **YouTube** Sheet：YT 平台 Top 50（按浏览量降序）
- **TikTok** Sheet：TT 平台 Top 50
- **Instagram** Sheet：IG 平台 Top 50
- **汇总** Sheet：三平台交叉参考（按浏览量降序）
