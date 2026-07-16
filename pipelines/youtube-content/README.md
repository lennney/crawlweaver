# YouTube Content Factory

> AI Agent 驱动的 YouTube 视频内容生产全流程平台。
> 每日采集热门 → Agent 分析趋势 → 自动生产视频 → SEO 优化 → 定时发布。

## 架构全景

```
① Trending Scout        ② AI Studio           ③ SEO Engine
┌─────────────────┐    ┌─────────────────┐    ┌──────────────┐
│ 每日采集热门      │    │ 视频二创+AI配音  │    │ 标题/描述/标签│
│ YT/TK/IG 三平台  │───▶│ Agent 分析趋势   │───▶│ 算法驱动优化  │
│ → SQLite/Postgres │    │ → 生成内容简报   │    │ Hook 生成     │
└─────────────────┘    │ → 执行剪辑+配音   │    └──────────────┘
        │              └─────────────────┘           │
        ▼                    ▼                       ▼
┌─────────────────────────────────────────────────────────────┐
│              ④ Account Tracker + ⑤ Daily Report              │
│  ┌──────────────────────┐    ┌──────────────────────────┐   │
│  │ 12 个账号自动采集      │    │ 每日 9:00 运营报表         │   │
│  │ 粉丝数追踪 + 涨粉分析  │    │ 表格/CSV 双格式输出        │   │
│  └──────────────────────┘    └──────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘

调度层：Cron
数据层：SQLite (dev) / PostgreSQL (prod)
```

## 实现路线

| Phase | 内容 | 状态 |
|-------|------|------|
| **Phase 0** | 项目基建（包结构、DB、CI） | ✅ 完成 |
| **Phase 1** | 双平台数据采集（YouTube + TikTok） | ✅ 完成 |
| **Phase 2** | 社媒趋势捕捉自动化（#tag 搜索 + 语言检测 + 账号追踪） | ✅ 完成 |
| **Phase 2.5** | 多平台账号追踪 + 每日运营报表（YouTube/TikTok/Instagram） | ✅ 完成 |
| **Phase 3** | CrewAI Agent 趋势分析 | 🔮 待定 |
| **Phase 4** | 视频生产管线 | 🔮 待定 |
| **Phase 5** | SEO + 发布 + Dashboard | 🔮 待定 |

详见 [docs/plans/2026-07-01-phase-0-1-v2.md](docs/plans/2026-07-01-phase-0-1-v2.md) |
详见 [docs/plans/2026-07-02-phase-2-trend-capture.md](docs/plans/2026-07-02-phase-2-trend-capture.md) |

## 技术栈

| 层 | 技术 | 选型理由 |
|----|------|---------|
| Agent 调度 | [CrewAI](https://github.com/crewAIInc/crewAI) (54k⭐, MIT) | 原生支持顺序 Agent 流水线 |
| 视频采集(YTB/TK) | [yt-dlp](https://github.com/yt-dlp/yt-dlp) (105k⭐, Unlicense) | 无需 API key，支持 YouTube/TikTok/Instagram |
| 视频采集(IG) | Instagram 公开 API + urllib | 无需登录，X-IG-App-ID 头 |
| 数据库 | SQLite (dev) / PostgreSQL 16 + SQLAlchemy | 零配置开发，生产可切换 |
| 语言检测 | 关键词匹配 + langid | 纯 Python，支持印尼/泰/英文 |
| 定时调度 | Cron (macOS 系统自带) | 每天 9:00 自动采集 |

## 快速开始

```bash
# 1. 安装依赖
uv sync
playwright install chromium  # TikTokApi 需要

# 2. 启动数据库
docker compose up -d

# 3. 运行数据库迁移
uv run alembic upgrade head

# 4. 采集 YouTube Trending Top 50
uv run python trending_aggregator/cli.py youtube

# 5. 采集 TikTok Trending Top 30
uv run python trending_aggregator/cli.py tiktok

# 6. 按 #tag 搜索高播视频（TikTok + YouTube）
uv run python trending_aggregator/cli.py tags

# 7. 自定义 tag 搜索（只搜 YouTube）
uv run python trending_aggregator/cli.py --platform youtube tags --tag-file data/tags.txt

# 8. 账号追踪管理
uv run python trending_aggregator/cli.py account list
uv run python trending_aggregator/cli.py account add --platform tiktok netflix
uv run python trending_aggregator/cli.py account fetch

# 9. 独立账号追踪模块（无 AI 依赖，推荐）
uv run python -m trending_aggregator.account_tracker list
uv run python -m trending_aggregator.account_tracker fetch
uv run python -m trending_aggregator.account_tracker fetch --detailed   # 真实 views/likes
uv run python -m trending_aggregator.account_tracker report --top 20
uv run python -m trending_aggregator.account_tracker export --format csv -o report.csv

# 10. 每日运营报表（昨日发布内容）
uv run python -m trending_aggregator.account_tracker daily-report
uv run python -m trending_aggregator.account_tracker daily-report --date 2026-07-09
uv run python -m trending_aggregator.account_tracker daily-report --format csv > daily.csv
```

## 项目结构

```
youtube-content-factory/
├── factory/                      # 核心库
│   ├── __init__.py
│   └── models.py                 # 数据库模型（含 tracked_tags, tracked_accounts）
├── trending_aggregator/          # 数据采集层（Phase 1+2 ✅）
│   ├── __init__.py
│   ├── protocol.py               # Scout ABC：数据源接口
│   ├── orchestrator.py           # 协调器：注册 → 抓取 → 评分 → 入库
│   ├── scorer.py                 # 热度分算法
│   ├── store.py                  # 持久化
│   ├── cli.py                    # 唯一 CLI 入口（含 tags, account 子命令）
│   ├── run_all.py                # 采集全部平台的快捷入口
│   ├── account_tracker/          # 独立账号追踪模块（无 AI 依赖）
│   │   ├── __init__.py           # 导出 AccountScout, TrackedAccount
│   │   ├── models.py             # TrackedAccount + VideoSnapshot + AccountSnapshot
│   │   ├── scout.py              # 三平台采集器（YT/TK/IG）
│   │   └── __main__.py           # CLI（list/add/remove/import/fetch/export/report/daily-report）
│   └── scouts/                   # 各平台采集器
│       ├── __init__.py
│       ├── youtube.py            # YouTubeScout (yt-dlp trending)
│       ├── tiktok.py             # TikTokScout (TikTokApi trending)
│       ├── language_filter.py    # 语言检测（关键词 + langid）
│       ├── tiktok_tag.py         # TikTokTagScout — #tag 趋势搜索采集器
│       ├── youtube_tag.py        # YouTubeTagScout — #tag 趋势搜索采集器
│       └── account.py            # AccountScout — 账号追踪采集器
├── tests/
│   ├── __init__.py
│   ├── test_trend_score.py       # 热度分测试
│   ├── test_scout.py             # 采集器测试
│   ├── test_language_filter.py   # 语言检测测试
│   └── test_tag_scout.py         # tag 采集器测试
├── data/
│   └── tags.txt                  # 默认 tag 列表（供 tags 子命令使用）
├── docs/
│   ├── arch/                     # 架构文档
│   ├── plans/                    # 实现计划
│   └── research/                 # 调研资料
├── docker-compose.yml            # PostgreSQL
├── Makefile                      # 常用命令
├── pyproject.toml                # 依赖管理
└── .env.example                  # 环境变量模板
```

## 核心原则

1. **上游能做的我们不写** — yt-dlp 做采集、CrewAI 做编排、SQLAlchemy 做 ORM
2. **TDD 先行** — 测试先写，代码后写
3. **渐进式交付** — Phase 0→1→2→3→4 逐步扩展，每阶段独立可验证
4. **MIT 生态** — 全部上游项目都是 MIT/Unlicense 许可
