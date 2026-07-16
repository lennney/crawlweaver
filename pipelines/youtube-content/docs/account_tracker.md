# 独立账号追踪模块 — account_tracker

位置：`trending_aggregator/account_tracker/`  
入口：`python -m trending_aggregator.account_tracker <命令>`

零外部 AI 依赖，只需 **yt-dlp** + **SQLAlchemy**。DB 默认共用 `dev.db`，可通过 `DATABASE_URL` 环境变量切换。

## 改进点

### 1. 精确数据（`--detailed`）

flat-playlist 模式下 YouTube 返回的 views = 0 —— 因为 yt-dlp 只读频道页元数据，不逐个访问视频页。

```
# 快但数据不准（YouTube views=0）
uv run python -m trending_aggregator.account_tracker fetch

# 慢但数据准（YouTube 真实 views/likes/comments）
uv run python -m trending_aggregator.account_tracker fetch --detailed
```

`--detailed` 对 YouTube 使用 `--no-flat-playlist`，每个视频独立抓取（慢 5-10x）。TikTok 不受影响。

> **什么时候用 detailed：** 首次建库、导出日报。日常巡检用默认模式。

### 2. 历史快照 — VideoSnapshot

每次 `fetch` 自动为每条视频写一行 `video_snapshots` 快照，含 views/likes/comments/shares + 时间戳。

一条 `video_id` 有多行，按 `fetched_at` 排序即是该视频的指标变化曲线：

```sql
-- 看某个视频的涨势
SELECT fetched_at, views, likes
FROM video_snapshots
WHERE video_id = 'tiktok:123456'
ORDER BY fetched_at;
```

表结构：

| 字段 | 说明 |
|------|------|
| `video_id` | `平台:原始ID`，如 `youtube:abc123` |
| `platform` | youtube / tiktok |
| `views / likes / comments / shares` | 该时刻的指标值 |
| `fetched_at` | 采集时间戳 |

### 3. 增量感知

每次 `fetch` 日志会报告 new / updated / total：

```
Account: 29 个账号 → 341 条视频 (new=312, updated=29)
```

- **new** — 该 `video_id` 从未出现过
- **updated** — views/likes 与上次快照不同
- **total** — 本批去重后的视频总数

### 4. 导出与报告

```
# CSV/JSON 导出
uv run python -m trending_aggregator.account_tracker export --format csv -o report.csv
uv run python -m trending_aggregator.account_tracker export --format json -o report.json

# 可选导出内容
uv run python -m trending_aggregator.account_tracker export --table accounts    # 账号列表
uv run python -m trending_aggregator.account_tracker export --table snapshots   # 全部快照
uv run python -m trending_aggregator.account_tracker export --table latest      # 各视频最新状态（默认）

# 统计摘要
uv run python -m trending_aggregator.account_tracker report --top 20 --days 7
```

`report` 输出：

```
📊 账号追踪报告（最近 7 天）

  活跃账号: 29
    tiktok: 26
    youtube: 3

    kdrama: 20

  快照总数: 2841
  近期采集: 2841 条

  采集日历:
    2026-07-03: 2841 条快照

  Top 20 视频（按播放量）:
      #        播放量       点赞       平台                          视频 ID  标题
    --------------------------------------------------------------------------------
      1  12,458,902  1,200,345    tiktok  tiktok:7123456789...  #kdrama #fyp
      ...
```

## 全部 CLI 命令

```bash
# 账号管理
uv run python -m trending_aggregator.account_tracker list [--platform tiktok] [--category kdrama] [--all]
uv run python -m trending_aggregator.account_tracker add --platform tiktok --category kdrama user1 user2
uv run python -m trending_aggregator.account_tracker remove 1
uv run python -m trending_aggregator.account_tracker import --file accounts.csv [--dry-run]

# 采集
uv run python -m trending_aggregator.account_tracker fetch [--detailed]

# 数据消费
uv run python -m trending_aggregator.account_tracker export [--format csv|json] [--output path] [--table accounts|snapshots|latest]
uv run python -m trending_aggregator.account_tracker report [--top 20] [--days 7]
```

## 与旧 CLI 的关系

`trending_aggregator/cli.py account` 子命令和 `trending_aggregator/account_tracker` 共享同一张 `tracked_accounts` 表（`dev.db`），可以混用。区别：

| | `cli.py account` | `account_tracker` |
|--|-----------------|-------------------|
| 依赖 | factory.models, orchestrator, protocol | 仅 SQLAlchemy + yt-dlp |
| 快照 | 无 | ✅ VideoSnapshot |
| detailed | 无 | ✅ --detailed |
| export/report | 无 | ✅ |
| 独立部署 | ❌ | ✅ |

后续分析推荐统一走 `account_tracker`。
