# 热门视频每日抓取工作流 — 实现计划

**日期:** 2026-06-30
**范围:** YouTube + TikTok 双平台热门视频抓取 → 筛选 → 表格输出
**状态:** 待审批

---

## 1. 需求概述

每日自动抓取 YouTube 和 TikTok 各分类下的热门视频，按浏览量/点赞数筛选，汇总成 CSV/Excel 表格，可选下载视频。

### 用户故事
- 作为内部运营团队，我希望每天看到各平台热门视频排行，以便快速发现热门内容趋势
- 作为内容分析师，我希望数据按分类+指标排序，便于对比分析

### 验收标准
1. YouTube 各分类 Top N 热门视频数据正确获取（≥14个分类）
2. TikTok 热门视频数据正确获取（按区域）
3. 数据按浏览量/点赞数排序，支持筛选阈值
4. 输出 CSV/Excel 表格，包含所有字段
5. 可选：视频下载到本地目录
6. 定时运行（Cron 或手动触发）

---

## 2. 技术选型

| 技术 | 为什么选它 | 考虑过的替代 | 选择原因 |
|------|-----------|-------------|---------|
| **YouTube Data API v3** | 官方API，零反爬 | yt-dlp（无热门端点）、RSS（仅频道） | 唯一官方热门数据源，10K quota/天够用 |
| **TikTok 付费API** | 稳定可靠，反爬由服务商处理 | curl_cffi（34%封锁率）、Playwright（22%） | 生产环境首选，$10-50/月 |
| **Python + pandas** | 数据处理标准 | openpyxl直接写 | pandas 的 ExcelWriter 一步到位 |
| **yt-dlp** | 视频下载 | youtube-dl（维护少） | 活跃维护，支持YouTube+TikTok |
| **Hermes Cron** | 定时触发 | Linux crontab、systemd timer | 与现有系统集成，支持通知 |

### TikTok API 服务商对比

| 服务商 | 价格 | 热门端点 | 可靠度 |
|--------|------|---------|--------|
| ScrapeCreators | ~$20/月 | ✅ trending feed | ⭐⭐⭐⭐ |
| SociaVault | ~$15/月 | ✅ discover + trending | ⭐⭐⭐⭐ |
| Scrapfly | ~$50/月 | ⚠️ 需自己构造 | ⭐⭐⭐⭐⭐ |

**推荐:** ScrapeCreators（性价比最高，有 trending 端点）

---

## 3. 架构设计

```
trending-scraper/
├── cli.py                  # CLI 入口
├── config.yaml             # 配置（API keys、分类、筛选阈值）
├── schema.py               # 统一数据模型
├── sources/
│   ├── __init__.py
│   ├── youtube.py          # YouTube Data API v3 封装
│   └── tiktok.py           # TikTok 付费API封装
├── pipeline/
│   ├── __init__.py
│   ├── fetch.py            # 并行抓取编排
│   ├── filter.py           # 筛选+排序
│   └── output.py           # CSV/Excel 输出
├── download/
│   ├── __init__.py
│   └── video.py            # yt-dlp 视频下载
├── tests/
│   ├── test_youtube.py
│   ├── test_tiktok.py
│   ├── test_filter.py
│   └── test_output.py
└── output/                 # 输出目录
    └── 2026-06-30/
        ├── trending.csv
        ├── trending.xlsx
        └── videos/         # 可选下载
```

### 数据模型（schema.py）

```python
from pydantic import BaseModel
from datetime import datetime
from enum import Enum

class Platform(str, Enum):
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"

class TrendingVideo(BaseModel):
    # 来源
    platform: Platform
    video_id: str
    url: str
    
    # 内容
    title: str
    description: str = ""
    channel: str = ""       # YouTube: 频道名, TikTok: 用户名
    category: str = ""      # YouTube: 分类名, TikTok: 标签/分类
    
    # 指标
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    
    # 时间
    published_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=datetime.now)
    
    # 可选下载
    local_path: str = ""
```

### 配置（config.yaml）

```yaml
youtube:
  api_key: "${YOUTUBE_API_KEY}"
  region_code: "US"
  categories: [10, 17, 20, 22, 23, 24, 25, 26, 27, 28]  # 分类ID
  max_results_per_category: 20

tiktok:
  api_key: "${TIKTOK_API_KEY}"
  provider: "scrapecreators"  # 或 sociault
  region: "US"
  max_results: 50

filter:
  min_views: 100000
  min_likes: 10000
  sort_by: "views"  # views | likes | comments
  sort_order: "desc"
  top_n: 50  # 每个平台取 top N

download:
  enabled: false
  output_dir: "output/{date}/videos"
  format: "best[height<=720]"  # 720p 节省空间

output:
  format: ["csv", "xlsx"]
  output_dir: "output/{date}"
```

---

## 4. 实现计划（TDD）

### Phase 1: 基础框架（Task 1-3）

#### Task 1: 项目初始化 + 数据模型
- [ ] 创建项目结构 `~/trending-scraper/`
- [ ] 初始化 `pyproject.toml`（uv 管理）
- [ ] 实现 `schema.py`（TrendingVideo Pydantic model）
- [ ] 写测试 `tests/test_schema.py`
- **验收:** `uv run pytest tests/test_schema.py` 通过

#### Task 2: 配置加载
- [ ] 实现 `config.py`（YAML 加载 + 环境变量替换）
- [ ] 写测试 `tests/test_config.py`
- **验收:** 配置文件正确加载，环境变量被替换

#### Task 3: CLI 入口
- [ ] 实现 `cli.py`（argparse: fetch / download / status）
- [ ] 写测试 `tests/test_cli.py`
- **验收:** `uv run python cli.py fetch --help` 显示帮助

### Phase 2: YouTube 源（Task 4-6）

#### Task 4: YouTube API 封装
- [ ] 实现 `sources/youtube.py`
  - `fetch_trending(region, category_id, max_results) -> list[TrendingVideo]`
  - `fetch_all_categories(region) -> list[TrendingVideo]`
  - Quota 管理（计数 + 预估）
- [ ] 写测试 `tests/test_youtube.py`（mock API 响应）
- **验收:** mock 测试通过，返回正确格式的 TrendingVideo

#### Task 5: YouTube 分类映射
- [ ] 实现分类 ID → 名称映射（14个主要分类）
- [ ] 支持按名称筛选分类
- **验收:** 输入 "Music" 返回 category_id=10

#### Task 6: YouTube 集成测试
- [ ] 用真实 API key 跑一次（需用户配置）
- [ ] 验证返回数据格式正确
- **验收:** `uv run python cli.py fetch --platform youtube` 输出非空

### Phase 3: TikTok 源（Task 7-9）

#### Task 7: TikTok API 封装
- [ ] 实现 `sources/tiktok.py`
  - `fetch_trending(region, max_results) -> list[TrendingVideo]`
  - 支持 ScrapeCreators / SociaVault 两种 provider
- [ ] 写测试 `tests/test_tiktok.py`（mock API 响应）
- **验收:** mock 测试通过

#### Task 8: TikTok 数据归一化
- [ ] 不同 API 返回格式 → 统一 TrendingVideo
- [ ] 处理缺失字段（TikTok 没有 comments 字段时填 0）
- **验收:** 两种 provider 返回格式一致

#### Task 9: TikTok 集成测试
- [ ] 用真实 API key 跑一次
- **验收:** `uv run python cli.py fetch --platform tiktok` 输出非空

### Phase 4: 管线 + 输出（Task 10-12）

#### Task 10: 并行抓取编排
- [ ] 实现 `pipeline/fetch.py`
  - `fetch_all(platforms, config) -> list[TrendingVideo]`
  - YouTube + TikTok 并行执行（ThreadPoolExecutor）
  - 错误隔离（一个平台失败不影响另一个）
- **验收:** 两个平台数据合并，格式统一

#### Task 11: 筛选 + 排序
- [ ] 实现 `pipeline/filter.py`
  - `filter_and_sort(videos, config) -> list[TrendingVideo]`
  - 按 min_views / min_likes 筛选
  - 按指定字段排序，取 top N
- **验收:** 筛选后数量 ≤ top_n，排序正确

#### Task 12: CSV/Excel 输出
- [ ] 实现 `pipeline/output.py`
  - `export_csv(videos, path)`
  - `export_excel(videos, path)`（pandas ExcelWriter）
  - 自动创建输出目录
- [ ] 写测试 `tests/test_output.py`
- **验收:** 生成的 CSV/Excel 可正常打开，数据完整

### Phase 5: 视频下载（Task 13-14）

#### Task 13: yt-dlp 下载封装
- [ ] 实现 `download/video.py`
  - `download_video(url, output_dir, format) -> str`
  - 支持 YouTube + TikTok
  - 进度回调
- **验收:** 下载的视频文件存在且可播放

#### Task 14: 下载批量执行
- [ ] 集成到 CLI: `cli.py download --input output/2026-06-30/trending.csv`
- [ ] 支持断点续传（已下载跳过）
- **验收:** 重复运行不重复下载

### Phase 6: 定时 + 交付（Task 15-16）

#### Task 15: 定时运行配置
- [ ] 配置 Hermes Cron Job（每日定时触发）
- [ ] 支持手动触发
- **验收:** cron job 正确创建

#### Task 16: 端到端验证
- [ ] 完整跑一次: fetch → filter → output
- [ ] 检查输出文件完整性
- **验收:** CSV/Excel 包含两个平台数据，字段完整

---

## 5. 依赖

```toml
[project]
dependencies = [
    "requests>=2.31",
    "pydantic>=2.0",
    "pandas>=2.0",
    "openpyxl>=3.1",      # Excel 写入
    "pyyaml>=6.0",
    "yt-dlp>=2024.1",     # 视频下载
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.12",
]
```

---

## 6. 风险 + 缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| YouTube API quota 不够 | 部分分类拿不到 | 优先高价值分类，缓存结果 |
| TikTok API key 过期/限流 | TikTok 数据中断 | 支持多 provider fallback |
| 视频下载被平台封IP | 下载失败 | 代理池 + 限速 |
| 分类数据为空（某些region） | 表格有空行 | 跳过空分类 |

---

## 7. 时间估算

| Phase | 内容 | 预估 |
|-------|------|------|
| Phase 1 | 基础框架 | 2-3小时 |
| Phase 2 | YouTube 源 | 3-4小时 |
| Phase 3 | TikTok 源 | 2-3小时 |
| Phase 4 | 管线+输出 | 2-3小时 |
| Phase 5 | 视频下载 | 1-2小时 |
| Phase 6 | 定时+验证 | 1小时 |
| **总计** | | **11-16小时** |

---

## 8. 下一步

1. 用户确认方案
2. 用户提供 API keys（YouTube Data API key + TikTok 付费API key）
3. 开始 Phase 1 实现
