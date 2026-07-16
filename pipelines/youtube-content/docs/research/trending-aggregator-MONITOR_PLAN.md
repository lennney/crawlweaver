# Video Monitor — 增量方案

**日期:** 2026-07-01
**状态:** 待 trending 核心跑通后执行
**定位:** 在 trending-video-aggregator 包内新增，共享 sources/schema/config

---

## 1. 与 Trending 的关系

```
trending-video-aggregator/
│
├── trending_aggregator/           ← 现有包
│   ├── config.py                  ← 共用
│   ├── schema.py                  ← 共用 VideoItem
│   ├── sources/                   ← 共用，但 API 调用不同
│   │   ├── youtube.py             ← + fetch_channel_videos()
│   │   ├── tiktok.py              ← + fetch_user_videos()
│   │   └── instagram.py           ← + fetch_user_reels()
│   │
│   ├── aggregator.py              ← trending 专用
│   ├── exporter.py                ← trending 专用
│   ├── main.py                    ← trending 入口
│   │
│   ├── monitor.py                 ← 🆕 监控入口
│   ├── storage.py                 ← 🆕 SQLite 持久化
│   ├── analytics.py               ← 🆕 趋势分析
│   └── report.py                  ← 🆕 趋势报告
│
├── tests/
│   ├── test_monitor.py
│   ├── test_storage.py
│   └── test_analytics.py
│
└── deploy/
    └── monitor.service + .timer   ← 🆕
```

**共享的：** `schema.VideoItem`、`config.Settings`、`sources/*.py` 中的 Client 初始化逻辑
**独立的：** 数据流（trending 是一次性导出文件，monitor 是时间序列写入 SQLite）

---

## 2. 数据流

```
用户输入                   每日定时执行
┌──────────┐              ┌──────────────────────┐
│ channel  │  一次配置    │  monitor.daily_fetch │
│ username │──────────▶──│     ↓     ↓     ↓    │──▶ SQLite ──▶ analytics ──▶ Excel
│ user_id  │              │  YT    TT    IG     │       │
└──────────┘              └──────────────────────┘       │
                                                   video_snapshots 表
                                                   (每视频每日一行)
```

区别于 trending：
- Trending：3 个平台 → aggregator 合并 → export 一个 Excel → 结束
- Monitor：3 个平台 → SQLite INSERT → 积累历史 → analytics 查询 → report 生成 Excel+图表

---

## 3. 模块设计

### 3.1 数据源扩展（sources/*.py 新增函数）

每个 sources 模块新增一个"获取频道/用户所有视频"函数：

#### YouTube

```python
def fetch_channel_videos(channel_url: str, max_videos: int = 50) -> List[VideoItem]:
    """获取频道全部视频（最新 N 个）"""
    # yt-dlp 支持频道 URL：https://www.youtube.com/@channelname/videos
    url = channel_url.rstrip('/') + '/videos'
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'extract_flat': 'in_playlist',
        'playlistend': max_videos,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(url, download=False)
    # ... 转换为 VideoItem 列表
```

> 区别于 `fetch_youtube_trending()`：URL 从 `/feed/trending` 变成 `/@channel/videos`，其余逻辑相同。

#### TikTok

```python
def fetch_user_videos(username: str, max_videos: int = 50) -> List[VideoItem]:
    """获取用户全部视频（最新 N 个）"""
    # TikTokApi v7：api.user(username=username).videos(count=max_videos)
    async with TikTokApi() as api:
        await api.create_sessions(ms_tokens=[settings.tiktok_sessionid], ...)
        user = api.user(username=username)
        async for video in user.videos(count=max_videos):
            # ... 转换为 VideoItem
```

#### Instagram

```python
def fetch_user_reels(username: str, max_videos: int = 50) -> List[VideoItem]:
    """获取用户全部 Reels（最新 N 个）"""
    cl = _get_client()
    user_id = cl.user_id_from_username(username)
    medias = cl.user_medias(user_id, amount=max_videos)
    # 筛选 product_type == 'clips' 的 Reels
```

> instagrapi 已有 `user_medias()`，只需加过滤逻辑。

---

### 3.2 SQLite 存储（storage.py）

```python
import sqlite3
from datetime import datetime
from typing import List

from .schema import VideoItem


DB_PATH = "monitor.db"


def init_db():
    """建表（幂等）"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS video_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                video_id TEXT NOT NULL,
                title TEXT,
                url TEXT,
                views INTEGER DEFAULT 0,
                likes INTEGER DEFAULT 0,
                comments INTEGER DEFAULT 0,
                shares INTEGER DEFAULT 0,
                fetched_at TEXT NOT NULL,
                UNIQUE(platform, video_id, fetched_at)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshot_time
            ON video_snapshots(platform, video_id, fetched_at)
        """)


def save_snapshots(videos: List[VideoItem], fetched_at: str = None):
    """批量写入当日快照"""
    if fetched_at is None:
        fetched_at = datetime.now().strftime('%Y-%m-%d %H:%M')

    with sqlite3.connect(DB_PATH) as conn:
        for v in videos:
            conn.execute("""
                INSERT OR IGNORE INTO video_snapshots
                (platform, video_id, title, url, views, likes, comments, shares, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (v.platform, v.video_id, v.title, v.url,
                  v.views, v.likes, v.comments, v.shares, fetched_at))
```

**设计要点：**
- `INSERT OR IGNORE` + `UNIQUE(platform, video_id, fetched_at)` — 同一天多次运行不重复写
- `fetched_at` 精确到分钟 — 如果一天跑两次，能看到日内变化

---

### 3.3 趋势分析（analytics.py）

```python
"""趋势分析引擎 — 纯 SQL 查询，不引入 pandas"""
import sqlite3
from typing import List, Dict
from datetime import datetime, timedelta


def get_video_timeline(platform: str, video_id: str, days: int = 7) -> List[Dict]:
    """单个视频的 views 时间序列"""
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    with sqlite3.connect("monitor.db") as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT fetched_at, views, likes, comments, shares
            FROM video_snapshots
            WHERE platform = ? AND video_id = ? AND fetched_at >= ?
            ORDER BY fetched_at ASC
        """, (platform, video_id, cutoff)).fetchall()
    return [dict(r) for r in rows]


def compute_metrics(platform: str, video_id: str) -> Dict:
    """计算单个视频的趋势指标"""
    rows = get_video_timeline(platform, video_id, days=7)
    if len(rows) < 2:
        return {"status": "insufficient_data"}

    today = rows[-1]
    yesterday = rows[-2]
    avg_views = sum(r['views'] for r in rows) / len(rows)

    # 日增长
    delta = today['views'] - yesterday['views']
    pct = (delta / yesterday['views'] * 100) if yesterday['views'] > 0 else 0

    # 趋势判定
    if today['views'] > avg_views * 2:
        trend = '🚀 爆款'
    elif len(rows) >= 3 and all(rows[-i]['views'] < rows[-i-1]['views'] for i in range(1, 4)):
        trend = '📉 衰退'
    elif delta > 0:
        trend = '📈 上升'
    elif delta < 0:
        trend = '📉 下降'
    else:
        trend = '➡️ 持平'

    return {
        'today_views': today['views'],
        'yesterday_views': yesterday['views'],
        'delta': delta,
        'pct_change': round(pct, 1),
        'avg_7d': round(avg_views),
        'trend': trend,
    }


def top_growing(platform: str, limit: int = 10) -> List[Dict]:
    """增长最快的视频（按日增长率排名）"""
    with sqlite3.connect("monitor.db") as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT video_id, title, url,
                   MAX(views) as latest_views,
                   COUNT(*) as snapshots
            FROM video_snapshots
            WHERE platform = ?
            GROUP BY video_id
            HAVING snapshots >= 2
            ORDER BY latest_views DESC
            LIMIT ?
        """, (platform, limit)).fetchall()

    results = []
    for r in rows:
        metrics = compute_metrics(platform, r['video_id'])
        results.append({**dict(r), **metrics})

    # 按增长率排序
    results.sort(key=lambda x: abs(x.get('delta', 0)), reverse=True)
    return results[:limit]
```

**分析指标总结：**

| 指标 | 计算方式 | 用途 |
|------|---------|------|
| 日增长量 | `today.views - yesterday.views` | 绝对变化 |
| 日增长率 | `delta / yesterday * 100` | 相对变化 |
| 7日均线 | `AVG(views) over 7 days` | 平滑波动 |
| 爆款标记 | `today > avg × 2` | 异常高亮 |
| 衰退标记 | 连续 3 天下降 | 预警 |

---

### 3.4 趋势报告（report.py）

```python
"""生成趋势分析报告 Excel"""
import openpyxl
from openpyxl.chart import LineChart, Reference
from datetime import datetime

from .analytics import compute_metrics, get_video_timeline, top_growing
from .config import settings


def generate_report() -> str:
    """生成趋势报告 Excel（分平台 Sheet + 图表）"""
    filename = f"monitor-report-{datetime.now():%Y%m%d}.xlsx"
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    for platform in ['youtube', 'tiktok', 'instagram']:
        ws = wb.create_sheet(title=platform.capitalize())

        # 表头
        headers = ['视频标题', '最新浏览量', '昨日浏览量', '日增长', '增长率%',
                   '7日均线', '趋势', '链接']
        for col, h in enumerate(headers, 1):
            ws.cell(row=1, column=col, value=h)

        # 数据行
        videos = top_growing(platform, limit=20)
        for row, v in enumerate(videos, 2):
            ws.cell(row=row, column=1, value=v.get('title', '')[:100])
            ws.cell(row=row, column=2, value=v.get('today_views', 0))
            ws.cell(row=row, column=3, value=v.get('yesterday_views', 0))
            ws.cell(row=row, column=4, value=v.get('delta', 0))
            ws.cell(row=row, column=5, value=v.get('pct_change', 0))
            ws.cell(row=row, column=6, value=v.get('avg_7d', 0))
            ws.cell(row=row, column=7, value=v.get('trend', ''))

    # 趋势图 Sheet（Top 5 增长最快视频的 views 曲线）
    ws_chart = wb.create_sheet('趋势图')
    chart = LineChart()
    chart.title = "Views Trend (7 days)"
    chart.y_axis.title = "Views"
    chart.x_axis.title = "Date"

    # 取总增长 Top 5 的视频画折线图
    all_videos = []
    for platform in ['youtube', 'tiktok', 'instagram']:
        all_videos.extend(top_growing(platform, limit=3))

    row = 1
    for v in sorted(all_videos, key=lambda x: abs(x.get('delta', 0)), reverse=True)[:5]:
        timeline = get_video_timeline(v.get('platform', ''), v['video_id'], days=7)
        if len(timeline) < 2:
            continue

        label = f"{v.get('title', v['video_id'])[:30]}"
        ws_chart.cell(row=row, column=1, value=label)
        for i, point in enumerate(timeline):
            ws_chart.cell(row=row, column=2 + i, value=point['views'])
        row += 1

    wb.save(filename)
    return filename
```

---

### 3.5 入口（monitor.py）

```python
"""监控入口 — 每日执行"""
import logging

from .config import settings
from .storage import init_db, save_snapshots
from .report import generate_report

logger = logging.getLogger(__name__)

# 从配置读要监控的频道列表
CHANNELS = {
    'youtube': [],     # ['https://www.youtube.com/@yourchannel']
    'tiktok': [],      # ['yourusername']
    'instagram': [],   # ['yourusername']
}


def daily_monitor():
    """每日抓取 + 存储 + 出报告"""
    init_db()
    logger.info("开始监控...")

    from .sources.youtube import fetch_channel_videos
    from .sources.tiktok import fetch_user_videos
    from .sources.instagram import fetch_user_reels

    all_videos = []

    for url in CHANNELS['youtube']:
        try:
            videos = fetch_channel_videos(url, max_videos=settings.top_n)
            save_snapshots(videos)
            all_videos.extend(videos)
            logger.info(f"YouTube {url}: {len(videos)} 条")
        except Exception as e:
            logger.error(f"YouTube {url} 失败: {e}")

    for username in CHANNELS['tiktok']:
        try:
            videos = fetch_user_videos(username, max_videos=settings.top_n)
            save_snapshots(videos)
            all_videos.extend(videos)
            logger.info(f"TikTok {username}: {len(videos)} 条")
        except Exception as e:
            logger.error(f"TikTok {username} 失败: {e}")

    for username in CHANNELS['instagram']:
        try:
            videos = fetch_user_reels(username, max_videos=settings.top_n)
            save_snapshots(videos)
            all_videos.extend(videos)
            logger.info(f"Instagram {username}: {len(videos)} 条")
        except Exception as e:
            logger.error(f"Instagram {username} 失败: {e}")

    if all_videos:
        report_file = generate_report()
        logger.info(f"报告: {report_file}")

    logger.info(f"监控完成，共 {len(all_videos)} 个视频")


if __name__ == '__main__':
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO)
    daily_monitor()
```

---

## 4. 配置扩展

config.py 新增：

```python
class Settings(BaseSettings):
    # ... 现有配置 ...

    # Monitor 配置
    monitor_channels_youtube: str = ''     # 逗号分隔的 URL 列表
    monitor_channels_tiktok: str = ''      # 逗号分隔的用户名列表
    monitor_channels_instagram: str = ''   # 逗号分隔的用户名列表
    monitor_top_n: int = 50                # 每个频道最多追踪视频数
    monitor_db_path: str = 'monitor.db'    # SQLite 路径
    monitor_retention_days: int = 90       # 保留天数
```

---

## 5. 部署

### systemd timer（独立于 trending）

```ini
# deploy/monitor.service
[Service]
Type=oneshot
ExecStart=/path/to/uv run python -m trending_aggregator.monitor
TimeoutStartSec=600

# deploy/monitor.timer
[Timer]
OnCalendar=09:30  # trending 跑完后 30 分钟
Persistent=true
```

---

## 6. 执行计划

| Phase | 内容 | 时间 |
|-------|------|------|
| **M1** | storage.py — SQLite 建表 + save_snapshots | 1h |
| **M2** | sources/*.py 新增 fetch_channel/fetch_user 函数 | 2h |
| **M3** | analytics.py — 日增长/7日均线/趋势判定 | 1.5h |
| **M4** | report.py — Excel 报告 + 折线图 | 1.5h |
| **M5** | monitor.py + config 扩展 + systemd 部署 | 1h |
| **M6** | 测试 + 端到端验证 | 1.5h |
| **合计** | | **~8.5h** |

---

## 7. 与 Trending 的协同

| 维度 | Trending | Monitor | 共享 |
|------|---------|---------|------|
| 触发 | `python -m trending_aggregator.main` | `python -m trending_aggregator.monitor` | config.py, schema.py |
| 定时 | 每日 09:00 | 每日 09:30 | deploy/*.timer |
| 数据源 | trending APIs | user/channel APIs | sources/ 模块 |
| 输出 | `trending-{date}.xlsx` | `monitor-report-{date}.xlsx` + `monitor.db` | exporter 逻辑可复用 |
| 存储 | 无 | SQLite（~90 天保留） | — |

**互补关系：** Trending 告诉你"外面什么火"，Monitor 告诉你"我的视频表现如何"。
