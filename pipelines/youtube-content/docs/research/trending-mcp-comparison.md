# 三方案详细对比

## 对比维度总览

| 维度 | 方案A: 组合现有+聚合层 | 方案B: 全自建 | 方案C: Trends-MCP |
|------|----------------------|-------------|-------------------|
| **工作量** | ~3-5h | ~15h | ~1h |
| **YouTube数据** | yt-dlp热门视频 ✅ | yt-dlp热门视频 ✅ | 趋势数据 ⚠️(非视频列表) |
| **TikTok数据** | lamatok API视频 ✅ | Playwright+cookies ✅ | 趋势数据 ⚠️(非视频列表) |
| **免费额度** | YouTube无限 + TikTok 100次/天 | 完全免费无限 | 100次/天 |
| **稳定性** | ⭐⭐⭐⭐ 高（成熟库） | ⭐⭐⭐ 中（需维护反爬） | ⭐⭐⭐⭐ 高（托管服务） |
| **可扩展性** | ⭐⭐⭐ 中（加平台=加MCP源） | ⭐⭐⭐⭐⭐ 高（完全控制） | ⭐⭐ 低（受限于API能力） |
| **维护成本** | 低（上游库维护） | 高（反爬策略需持续更新） | 低（服务商维护） |
| **数据丰富度** | ⭐⭐⭐⭐ 详细字段 | ⭐⭐⭐⭐⭐ 完全自定义 | ⭐⭐ 有限字段 |

---

## 方案A: 组合现有 + 聚合层（推荐）

### 架构
```
Hermes Agent
  │
  ├── mcp_youtube_trending (youtube-trending-mcp, PyPI)
  │   └── tools: search_trending, get_video_info
  │
  ├── mcp_lamatok (lamatok-mcp, npm)
  │   └── tools: search_videos, get_user_info, get_hashtag_info
  │
  └── mcp_trending聚合 (自写, ~200行Python)
      ├── fetch_youtube_trending() → 调 youtube-trending-mcp
      ├── fetch_tiktok_trending() → 调 lamatok-mcp
      ├── merge_and_filter() → 合并+筛选
      └── export_csv/xlsx() → 导出
```

### 优点
- ✅ **最快落地** — 3-5小时搞定
- ✅ **YouTube完全免费** — yt-dlp无限制
- ✅ **TikTok有100次免费** — 日常够用
- ✅ **上游维护** — 库有社区维护，不用自己修反爬
- ✅ **已验证** — youtube-trending-mcp 有100+ GitHub stars

### 缺点
- ⚠️ TikTok 100次/天可能不够（大量分类时）
- ⚠️ 依赖两个外部MCP，任一挂了影响整体
- ⚠️ 聚合层需要自己维护

### 安装步骤
```bash
# YouTube MCP
pip install youtube-trending-mcp

# TikTok MCP
npm install -g lamatok-mcp

# 注册到 Hermes
hermes config set mcp_servers.youtube_trending.command uvx
hermes config set mcp_servers.youtube_trending.args '["youtube-trending-mcp"]'
hermes config set mcp_servers.lamatok.command npx
hermes config set mcp_servers.lamatok.args '["-y", "lamatok-mcp"]'
```

### 聚合层核心逻辑（~200行）
```python
# 伪代码
def fetch_all_trending(region="US", categories=None):
    # 1. 调 youtube-trending-mcp 获取 YouTube 热门
    yt_videos = call_mcp("youtube_trending", "search_trending", 
                         region=region, categories=categories)
    
    # 2. 调 lamatok-mcp 获取 TikTok 热门
    tt_videos = call_mcp("lamatok", "search_videos",
                         query="trending", region=region)
    
    # 3. 合并 + 去重 + 排序
    all_videos = normalize_and_merge(yt_videos, tt_videos)
    
    return sorted(all_videos, key=lambda x: x.views, reverse=True)
```

---

## 方案B: 全自建

### 架构
```
trending-mcp/
├── server.py              # MCP Server (FastMCP)
├── sources/
│   ├── youtube.py         # yt-dlp 直接调用（免费无限）
│   └── tiktok.py          # Playwright + cookies（你有cookies）
├── tools/
│   ├── fetch_youtube.py
│   ├── fetch_tiktok.py
│   ├── fetch_all.py
│   ├── export.py
│   └── download.py
└── schema.py
```

### 优点
- ✅ **完全免费无限** — YouTube用yt-dlp，TikTok用cookies
- ✅ **完全控制** — 字段、格式、筛选逻辑全自定义
- ✅ **无外部依赖** — 不依赖第三方MCP服务
- ✅ **可扩展** — 加Facebook/Instagram只需加source

### 缺点
- ❌ **工作量大** — 15h+
- ❌ **TikTok反爬维护** — cookies会过期，Playwright需更新
- ❌ **需要你提供cookies** — YouTube cookies + TikTok cookies
- ❌ **稳定性风险** — 反爬策略变化时需手动修复

### TikTok cookies 方案细节
```python
# 用 Playwright + cookies 访问 TikTok
from playwright.async_api import async_playwright

async def fetch_tiktok_trending(cookies_path, region="US"):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        
        # 加载 cookies
        cookies = json.load(open(cookies_path))
        await context.add_cookies(cookies)
        
        page = await context.new_page()
        await page.goto(f"https://www.tiktok.com/trending?region={region}")
        
        # 拦截 API 响应获取数据
        videos = []
        page.on("response", lambda resp: 
            videos.append(resp.json()) 
            if "api/recommend/item_list" in resp.url else None
        )
        
        # 滚动加载更多
        for _ in range(5):
            await page.evaluate("window.scrollBy(0, 1000)")
            await page.wait_for_timeout(2000)
        
        return videos
```

---

## 方案C: Trends-MCP 一个搞定

### 架构
```
Hermes Agent
  │
  └── mcp_trends (Trends-MCP, PyPI)
      └── tools: 
          ├── youtube_search_trends (搜索趋势，非视频列表)
          ├── tiktok_hashtag_trends (标签趋势)
          ├── reddit_trending
          ├── google_trends
          └── ... 12+ 平台
```

### 优点
- ✅ **最简单** — 一个MCP搞定所有平台
- ✅ **12+平台** — YouTube/TikTok/Reddit/Google Trends等
- ✅ **免费100次/天** — 日常够用
- ✅ **零维护** — 服务商维护

### 缺点
- ❌ **不是视频列表** — 只有趋势数据（搜索量、增长率），没有具体视频
- ❌ **无法筛选浏览量/点赞数** — 数据维度有限
- ❌ **100次/天限制** — 多平台同时查可能不够
- ❌ **不适合你的需求** — 你要的是"热门视频排行"，不是"搜索趋势"

---

## 结论

| 你的需求 | 最佳方案 |
|----------|---------|
| **快速验证** | 方案A（3h搞定） |
| **长期生产** | 方案B（完全控制） |
| **只是看看趋势** | 方案C（但不满足你的需求） |

**我的建议：先用方案A验证需求，确认数据有用后再决定是否投入方案B。**

---

## 你的cookies情况

你提到有cookies，需要确认：

| 平台 | 需要什么cookies | 用途 |
|------|----------------|------|
| YouTube | `cookies.txt`（Netscape格式） | yt-dlp `--cookies cookies.txt` |
| TikTok | 浏览器session cookies（JSON格式） | Playwright `context.add_cookies()` |

**获取方式：**
- Chrome扩展 "Get cookies.txt LOCALLY" → 导出为 cookies.txt
- 或 `yt-dlp --cookies-from-browser chrome` 自动提取
