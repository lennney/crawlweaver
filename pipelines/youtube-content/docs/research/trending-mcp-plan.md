# 热门视频抓取 MCP Server — 方案设计

**日期:** 2026-06-30
**定位:** MCP Server，供 Hermes / Claude Code / 其他 Agent 系统调用
**状态:** 待审批

---

## 1. 定位

不是独立 CLI 工具，而是 **MCP Server**：
- 其他系统通过 MCP 协议调用
- 暴露 5 个工具（tools），Agent 按需调用
- 复用已有账号/API Key，不自建账号体系

**调用场景示例：**
```
用户: "帮我看看今天 YouTube 和 TikTok 有什么热门视频"
  → Agent 调用 mcp_trending_fetch_all(platforms=["youtube","tiktok"])
  → 返回结构化 JSON
  → Agent 汇总呈现

用户: "筛选浏览量 >100万的，导出 Excel"
  → Agent 调用 mcp_trending_export(min_views=1000000, format="xlsx")
  → 返回文件路径
```

---

## 2. 架构

```
trending-mcp/
├── server.py              # MCP Server 入口（stdio 传输）
├── tools/                 # MCP 工具定义
│   ├── fetch_youtube.py   # YouTube 热门抓取
│   ├── fetch_tiktok.py    # TikTok 热门抓取
│   ├── fetch_all.py       # 双平台聚合
│   ├── export.py          # 筛选+导出 CSV/Excel
│   └── download.py        # 视频下载
├── sources/               # 平台数据源
│   ├── youtube.py         # YouTube Data API v3 封装
│   └── tiktok.py          # TikTok 付费API 封装
├── schema.py              # 统一数据模型
├── config.py              # 配置管理（环境变量 + .env）
├── pyproject.toml
└── tests/
```

---

## 3. MCP 工具定义

### Tool 1: `fetch_youtube_trending`

```json
{
  "name": "fetch_youtube_trending",
  "description": "获取 YouTube 各分类热门视频",
  "inputSchema": {
    "type": "object",
    "properties": {
      "region": { "type": "string", "default": "US", "description": "地区代码" },
      "categories": { 
        "type": "array", 
        "items": { "type": "string" },
        "description": "分类名称列表，如 ['Music', 'Gaming', 'Science & Technology']。为空则全部分类"
      },
      "max_results": { "type": "integer", "default": 20, "description": "每分类最多返回数量" }
    }
  },
  "returnSchema": {
    "type": "array",
    "items": { "$ref": "#/TrendingVideo" }
  }
}
```

### Tool 2: `fetch_tiktok_trending`

```json
{
  "name": "fetch_tiktok_trending",
  "description": "获取 TikTok 热门视频",
  "inputSchema": {
    "type": "object",
    "properties": {
      "region": { "type": "string", "default": "US" },
      "max_results": { "type": "integer", "default": 50 }
    }
  }
}
```

### Tool 3: `fetch_all_trending`

```json
{
  "name": "fetch_all_trending",
  "description": "同时获取 YouTube + TikTok 热门视频，合并返回",
  "inputSchema": {
    "type": "object",
    "properties": {
      "platforms": { 
        "type": "array", 
        "items": { "type": "string", "enum": ["youtube", "tiktok"] },
        "default": ["youtube", "tiktok"]
      },
      "region": { "type": "string", "default": "US" },
      "max_results_per_platform": { "type": "integer", "default": 50 }
    }
  }
}
```

### Tool 4: `export_trending`

```json
{
  "name": "export_trending",
  "description": "筛选并导出热门视频为 CSV 或 Excel 文件",
  "inputSchema": {
    "type": "object",
    "properties": {
      "videos": { "type": "array", "description": "视频列表（上一步返回的 JSON）" },
      "min_views": { "type": "integer", "default": 0 },
      "min_likes": { "type": "integer", "default": 0 },
      "sort_by": { "type": "string", "enum": ["views", "likes", "comments"], "default": "views" },
      "top_n": { "type": "integer", "default": 50 },
      "format": { "type": "string", "enum": ["csv", "xlsx"], "default": "xlsx" },
      "output_path": { "type": "string", "description": "输出路径，为空则自动生成" }
    }
  },
  "returnSchema": {
    "type": "object",
    "properties": {
      "file_path": { "type": "string" },
      "total_count": { "type": "integer" },
      "platforms_breakdown": { "type": "object" }
    }
  }
}
```

### Tool 5: `download_video`

```json
{
  "name": "download_video",
  "description": "下载指定视频到本地",
  "inputSchema": {
    "type": "object",
    "properties": {
      "url": { "type": "string", "description": "视频 URL" },
      "output_dir": { "type": "string", "default": "./downloads" },
      "format": { "type": "string", "default": "best[height<=720]" }
    }
  },
  "returnSchema": {
    "type": "object",
    "properties": {
      "local_path": { "type": "string" },
      "size_mb": { "type": "number" }
    }
  }
}
```

### Tool 6: `list_youtube_categories`

```json
{
  "name": "list_youtube_categories",
  "description": "列出 YouTube 可用分类及其 ID",
  "inputSchema": {
    "type": "object",
    "properties": {
      "region": { "type": "string", "default": "US" }
    }
  }
}
```

---

## 4. 统一数据模型

```python
from pydantic import BaseModel
from datetime import datetime

class TrendingVideo(BaseModel):
    platform: str          # "youtube" | "tiktok"
    video_id: str
    url: str
    title: str
    description: str = ""
    channel: str = ""      # YouTube: 频道名, TikTok: 用户名
    category: str = ""     # YouTube: 分类名, TikTok: 标签
    thumbnail: str = ""    # 封面图URL
    
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    duration: str = ""     # "PT5M30S" 格式
    
    published_at: str = ""
    fetched_at: str = ""
```

---

## 5. 配置方案

环境变量（通过 `.env` 或系统环境注入）：

```bash
# YouTube
YOUTUBE_API_KEY=AIza...          # Google Cloud Console 申请

# TikTok（选一个）
TIKTOK_SCRAPECREATORS_KEY=...    # ScrapeCreators API key
# 或
TIKTOK_SOCIAULT_KEY=...          # SociaVault API key

# 可选
TRENDING_DEFAULT_REGION=US
TRENDING_OUTPUT_DIR=./output
```

MCP Server 注册（`~/.hermes/config.yaml`）：

```yaml
mcp_servers:
  trending:
    command: "uv"
    args: ["run", "--project", "/home/ubuntu/trending-mcp", "python", "server.py"]
    env:
      YOUTUBE_API_KEY: "${YOUTUBE_API_KEY}"
      TIKTOK_SCRAPECREATORS_KEY: "${TIKTOK_SCRAPECREATORS_KEY}"
    timeout: 60
```

---

## 6. 实现任务拆解

### Phase 1: 基础（Task 1-3）~3h

| Task | 内容 | 验收 |
|------|------|------|
| 1 | 项目初始化 + pyproject.toml + schema.py | `uv run pytest` 通过 |
| 2 | config.py（.env + 环境变量加载） | 配置正确读取 |
| 3 | server.py（MCP Server 骨架，stdio 传输） | `uv run python server.py` 启动不报错 |

### Phase 2: YouTube 源（Task 4-5）~4h

| Task | 内容 | 验收 |
|------|------|------|
| 4 | sources/youtube.py（API 封装 + 分类映射） | mock 测试通过 |
| 5 | tools/fetch_youtube.py（MCP 工具） | Agent 可调用，返回 JSON |

### Phase 3: TikTok 源（Task 6-7）~3h

| Task | 内容 | 验收 |
|------|------|------|
| 6 | sources/tiktok.py（付费API封装） | mock 测试通过 |
| 7 | tools/fetch_tiktok.py（MCP 工具） | Agent 可调用 |

### Phase 4: 聚合 + 导出（Task 8-9）~3h

| Task | 内容 | 验收 |
|------|------|------|
| 8 | tools/fetch_all.py + tools/export.py | 双平台聚合 + 筛选导出 |
| 9 | CSV/Excel 输出（pandas） | 文件可打开，数据完整 |

### Phase 5: 下载 + 集成（Task 10-11）~2h

| Task | 内容 | 验收 |
|------|------|------|
| 10 | tools/download.py（yt-dlp 封装） | 视频下载成功 |
| 11 | 端到端测试 + Hermes 配置 | Agent 可完整调用 |

### 总计：~15h

---

## 7. 风险

| 风险 | 缓解 |
|------|------|
| YouTube API quota 不够（10K/天） | 缓存结果，避免重复调用 |
| TikTok API key 过期 | 支持多 provider fallback |
| MCP Server 启动慢 | uv 预编译 + 依赖缓存 |
| 视频下载被封IP | 代理池 + 限速（非核心功能，可降级） |

---

## 8. 你需要准备的

1. **YouTube Data API Key** — [Google Cloud Console](https://console.cloud.google.com/) 创建，启用 YouTube Data API v3
2. **TikTok API Key** — [ScrapeCreators](https://scrapecreators.com/) 注册（~$20/月）
3. **已有账号说明** — 你提到"借助已有的账号去做"，请说明是哪个系统的账号？

---

## 9. 下一步

1. 确认方案
2. 提供 API Keys
3. 开始 Phase 1 实现
