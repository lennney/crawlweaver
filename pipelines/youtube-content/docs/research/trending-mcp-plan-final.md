# 四平台热门视频抓取 — 完整方案（终版）

**日期:** 2026-06-30
**状态:** 待审批

---

## 平台可行性总结

| 平台 | 免费方案 | 现成MCP | 难度 | 结论 |
|------|---------|---------|------|------|
| YouTube | ✅ yt-dlp无限免费 | ✅ youtube-trending-mcp | ⭐ | 直接装 |
| TikTok | ✅ lamatok 100次/天 | ✅ lamatok-mcp | ⭐⭐ | 直接装 |
| Instagram | ✅ instagrapi免费(cookies) | ⚠️ 无现成trending MCP | ⭐⭐⭐ | 自建封装 |
| Facebook | ❌ 无免费方案 | ⚠️ 只有付费 | ⭐⭐⭐⭐⭐ | 跳过 |

---

## Phase 1: YouTube + TikTok（3-5h）

### 安装现有MCP

```bash
# YouTube（PyPI, yt-dlp驱动, 完全免费）
pip install youtube-trending-mcp

# TikTok（npm, lamatok API, 100次免费/天）
npm install -g lamatok-mcp
```

### 注册到Hermes

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  youtube_trending:
    command: "uvx"
    args: ["youtube-trending-mcp"]
    timeout: 60

  lamatok:
    command: "npx"
    args: ["-y", "lamatok-mcp"]
    timeout: 60
```

### 聚合层（自写 ~200行）

暴露给Agent的工具：

| 工具 | 功能 |
|------|------|
| `fetch_youtube_trending` | YouTube各分类热门视频 |
| `fetch_tiktok_trending` | TikTok热门视频 |
| `fetch_all_trending` | 双平台聚合 |
| `export_trending` | 筛选+导出CSV/Excel |

---

## Phase 2: Instagram（需开发 ~5h）

### 方案：instagrapi + FastMCP

```python
# 核心代码骨架
from instagrapi import Client
from fastmcp import FastMCP

cl = Client()
cl.login_by_sessionid("YOUR_SESSIONID")  # 浏览器cookies

mcp = FastMCP("instagram-trending")

@mcp.tool()
def fetch_instagram_reels(amount=30):
    """获取Instagram Explore热门Reels"""
    reels = cl.explore_reels(amount=amount)
    return [{"id": r.id, "title": r.title, "views": r.play_count, 
             "likes": r.like_count, "url": r.video_url} for r in reels]

@mcp.tool()
def fetch_hashtag_reels(tag, amount=50):
    """按标签获取热门Reels"""
    medias = cl.hashtag_medias_reels(tag, amount=amount)
    return [{"id": m.id, "title": m.title, "views": m.play_count,
             "likes": m.like_count} for m in medias]
```

### 依赖
- `instagrapi` — 8k★, 活跃维护
- `fastmcp` — MCP Server 框架
- 浏览器导出的 `sessionid` cookie

### 风险
- Instagram 会封异常登录（需用稳定IP）
- sessionid 过期需重新登录
- `explore_reels()` 返回的是个性化推荐，不是全局热门

---

## Phase 3: Facebook（建议跳过）

### 为什么跳过
1. Meta 没有"热门视频"API端点
2. 所有开源爬虫都已过时/失效
3. Facebook Watch 的热门内容需要重度JS渲染 + 反爬对抗
4. 维护成本远大于收益

### 如果一定要做
- Apify Facebook Videos Scraper（MCP, $2.99/1000条）
- 或 ScrapeCreators（MCP, 多平台）

---

## 数据模型（四平台统一）

```python
class TrendingVideo(BaseModel):
    platform: str          # "youtube" | "tiktok" | "instagram"
    video_id: str
    url: str
    title: str
    description: str = ""
    channel: str = ""      # 创作者名称
    category: str = ""     # 分类/标签
    thumbnail: str = ""
    
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    
    published_at: str = ""
    fetched_at: str = ""
```

---

## 配置

```bash
# 环境变量（.env）
YOUTUBE_API_KEY=           # YouTube不需要，yt-dlp免费
TIKTOK_SESSION_ID=         # lamatok不需要key
INSTAGRAM_SESSION_ID=      # 从浏览器DevTools提取
```

---

## 总工作量

| Phase | 内容 | 工作量 | 依赖 |
|-------|------|--------|------|
| 1 | YouTube + TikTok（装现有+聚合） | 3-5h | 无 |
| 2 | Instagram（instagrapi封装） | 5h | Phase 1 |
| 3 | Facebook（跳过） | 0h | — |
| **总计** | | **8-10h** | |

---

## 下一步

1. 确认方案
2. 提供 Instagram sessionid cookie
3. 开始 Phase 1（装现成MCP）
