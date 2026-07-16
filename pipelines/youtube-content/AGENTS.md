# YouTube Content Factory

AI Agent 驱动的 YouTube 视频内容生产全流程平台——每日采集热门 → Agent 分析趋势 → 自动生产视频 → SEO 优化 → 定时发布。

## 初始化（新 agent 首次进入）

```bash
# 1. 读 README.md 了解全景
cat README.md

# 2. 读当前计划
cat docs/plans/2026-07-01-phase-0-1-v2.md

# 3. 读 HANDOVER.md 看上次进展
cat HANDOVER.md

# 4. 检查 hooks 是否生效
ls .hooks/
```

## 命令

```bash
# 安装依赖
uv sync
playwright install chromium  # TikTokApi 需要

# 启动数据库
make db-up

# 迁移
uv run alembic upgrade head

# 跑测试
make test

# 采集热门视频（全部平台）
make scout

# 只采集 YouTube
make scout-youtube

# 只采集 TikTok
make scout-tiktok

# 按 #tag 搜索高播视频（全部平台）
make scout-tags

# 按 #tag 搜索（只搜 YouTube）
make scout-tags-youtube

# 账号追踪 — 列出追踪列表
make account-list

# 账号追踪 — 添加账号
make account-add

# 账号追踪 — 运行采集
make account-fetch

# 每日运营报表
make account-daily-report

# CSV 导出
uv run python -m trending_aggregator.account_tracker export --format csv -o report.csv

# 手动触发 hook 测试
bash .hooks/on-session-start.sh
```

## 技术栈

Python 3.12 / SQLAlchemy 2.0 / yt-dlp + urllib (Instagram API) / Cron

## 约束（按优先级）

1. 所有密钥从 `.env` 读取，禁止硬编码
2. **上游能做的我们不写** — yt-dlp 做采集、SQLAlchemy 做 ORM
3. 测试覆盖率不低于 80%（`make test`）
4. 数据库迁移只能 ADD，不能 DROP/RENAME

## 边界

- ✅ **Always:** 运行测试、更新 HANDOVER.md、修复 lint、读 `docs/arch/` 中的架构文档
- ⚠️ **Ask:** 加依赖、改 schema、改 API 签名、换技术栈
- 🚫 **Never:** 硬编码密钥、删除测试、改已有迁移、跳过 verify 步骤

## 陷阱（症状 → 原因 → 解决）

- `uv sync` 失败 → Python 版本不对 → 确保 Python ≥ 3.12
- TikTok 采集返回空 → TikTokApi 依赖 Playwright + chromium → `playwright install chromium`
- TikTok 粉丝数为空 → 页面被限流 → 等几分钟重试
- YouTube 无 /videos tab → 账号可能只有 Shorts → 自动回退到频道主页
- PostgreSQL 连不上 → docker 没启动 → `make db-up`
- 数据库迁移冲突 → 多人改 schema → `alembic merge heads` 合并

## 钩子系统

本项目使用 `agent-workspace-refarch` 的标准化 hook 系统：

| 平台 | 配置文件 | 事件 |
|------|---------|------|
| Claude Code | `.claude/settings.json` | SessionStart / PreToolUse / PostToolUse / SessionEnd |
| Codex | `hooks.json` | SessionStart / PreToolUse / PostToolUse / Stop |
| Hermes | `~/.hermes/config.yaml` | on_session_start / on_session_end / pre_tool_call / post_tool_call |

所有 hook 脚本在 `.hooks/` 目录，三平台共用一份。

## Agent 规则

1. **每次任务完成后更新 HANDOVER.md** — 记录做了什么、关键决策、下一步
2. **踩到新坑时记录** — `bash .hooks/on-lesson.sh "<问题>" 踩坑`
3. **发现有价值的架构洞察时** — `bash .hooks/on-lesson.sh "<发现>" 发现`
4. **重复出现的坑写入上方"陷阱"段**（三段式：症状→原因→解决）
5. **改跨模块代码前读所有相关模块的文档** — 参考 `docs/arch/`
6. **架构级决策写 ADR 到 `docs/arch/decisions/`**

## 项目结构

```
youtube-content-factory/
├── .hooks/                      # 共享 hook 脚本（三平台）
├── .claude/settings.json        # Claude Code hook 配置
├── hooks.json                   # Codex hook 配置
├── handover.sh                  # /handover 命令
│
├── factory/                     # 核心库
│   ├── __init__.py
│   └── models.py               # TrendingVideo + Video + TrackedTag + TrackedAccount
├── trending_aggregator/         # 数据采集层（Phase 1+2 ✅）
│   ├── __init__.py
│   ├── protocol.py               # Scout ABC：数据源接口
│   ├── orchestrator.py           # 协调器：注册 → 抓取 → 评分 → 入库
│   ├── scorer.py                 # 热度分算法
│   ├── store.py                  # 持久化
│   ├── cli.py                    # 唯一 CLI 入口（含 tags, account 子命令）
│   ├── run_all.py                # 采集全部平台的快捷入口
│   ├── account_tracker/          # 独立账号追踪模块（无 AI 依赖）
│   │   ├── __init__.py           # 导出 AccountScout, TrackedAccount
│   │   ├── models.py             # 自包含模型（TrackedAccount + VideoSnapshot + AccountSnapshot）
│   │   ├── scout.py              # 采集器 — YouTube(yt-dlp) + TikTok(yt-dlp/HTTP) + Instagram(API)
│   │   └── __main__.py           # CLI（list/add/remove/import/fetch/export/report/daily-report）
│   └── scouts/                   # 各平台采集器
│       ├── __init__.py
│       ├── youtube.py            # YouTubeScout (yt-dlp trending)
│       ├── tiktok.py             # TikTokScout (TikTokApi trending)
│       ├── language_filter.py    # 语言检测（关键词 + langid）
│       ├── tiktok_tag.py         # TikTokTagScout — #tag 趋势搜索
│       ├── youtube_tag.py        # YouTubeTagScout — #tag 趋势搜索
│       └── account.py            # AccountScout — 账号追踪
├── tests/                       # 测试（20/20 通过）
│
├── docs/
│   ├── arch/                    # 架构设计（ARCHITECTURE.md + AGENT_ARCHITECTURE.md）
│   ├── plans/                   # 实现计划（当前：Phase 0-1 v2）
│   └── research/                # 调研资料
│
├── data/
│   └── tags.txt                  # 默认 #tag 列表（供 tags 子命令使用）
├── pyproject.toml               # 依赖管理
├── docker-compose.yml           # PostgreSQL
├── Makefile                     # 常用命令
├── README.md                    # 项目全景
└── .env.example                 # 环境变量模板
```

## 参考

- [agent-workspace-refarch](https://github.com/lennney/agent-workspace-refarch) — 三层 AGENTS.md + HANDOVER.md + hooks 体系
- [docs/account_tracker.md](docs/account_tracker.md) — 独立账号追踪模块文档
- [docs/arch/ARCHITECTURE.md](docs/arch/ARCHITECTURE.md) — 平台架构设计
- [docs/arch/AGENT_ARCHITECTURE.md](docs/arch/AGENT_ARCHITECTURE.md) — CrewAI Agent 调度设计
- [docs/plans/2026-07-01-phase-0-1-v2.md](docs/plans/2026-07-01-phase-0-1-v2.md) — Phase 0-1 实现计划（已完成）
- [docs/plans/2026-07-02-phase-2-trend-capture.md](docs/plans/2026-07-02-phase-2-trend-capture.md) — Phase 2 社媒趋势捕捉自动化（已完成 ✅）
- [data/tags.txt](data/tags.txt) — 默认 #tag 列表
