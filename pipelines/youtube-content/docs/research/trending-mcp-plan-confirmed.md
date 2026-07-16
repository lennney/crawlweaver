# 热门视频定时抓取 — 最终方案（已确认）

**日期:** 2026-06-30
**状态:** ✅ 已确认，待执行

---

## 架构：两层设计

```
Layer 1: 工具层（核心，免费，快速）
├── 按区域 + 分类 获取热门视频
├── 按浏览量/点赞数排序
└── 输出 CSV/Excel 表格

Layer 2: AI增强层（可选，后续按需开启）
├── 内容标签自动分类
├── 跨平台话题匹配
└── 趋势变化检测
```

**先跑通 Layer 1，Layer 2 以后按需加。**

---

## 平台方案

| 平台 | 方案 | 成本 | 状态 |
|------|------|------|------|
| YouTube | youtube-trending-mcp (PyPI) | 免费无限 | 可立即安装 |
| TikTok | lamatok-mcp (npm) | 免费100次/天 | 可立即安装 |
| Instagram | instagrapi 封装 (自写MCP) | 免费(cookies) | Phase 2 |
| Facebook | 跳过 | — | 无免费方案 |

---

## 定时任务流程

```
Hermes Cron（每日 09:00）
  │
  ├── 1. fetch_youtube_trending(region, categories)
  ├── 2. fetch_tiktok_trending(region)
  ├── 3. fetch_instagram_reels(region)
  │
  ├── 4. filter_and_sort(min_views, top_n)
  │
  ├── 5. export_to_csv/excel → output/trending-{date}.xlsx
  │
  └── 6. deliver（飞书/Telegram 推送 top 10 摘要）
```

---

## Phase 1 执行计划（3-5h）

| Task | 内容 | 验收 |
|------|------|------|
| 1 | 安装 youtube-trending-mcp + lamatok-mcp | `uvx youtube-trending-mcp --help` 正常 |
| 2 | 注册到 Hermes config.yaml | `hermes mcp list` 显示两个server |
| 3 | 写聚合层 trending_aggregator.py (~200行) | 合并+筛选+排序逻辑正确 |
| 4 | 导出 CSV/Excel | 文件可打开，数据完整 |
| 5 | 配置 Hermes Cron 定时任务 | cron job 创建成功 |
| 6 | 端到端测试 | 完整跑一次，输出文件 |

---

## Phase 2 执行计划（5h，后续）

| Task | 内容 | 验收 |
|------|------|------|
| 7 | instagrapi 安装 + cookies 登录 | `cl.explore_reels()` 返回数据 |
| 8 | 封装成 MCP Server (~300行) | Agent 可调用 |
| 9 | 集成到聚合层 | 三平台数据合并 |
| 10 | 可选：AI增强层设计 | prompt + 分类逻辑 |

---

## 文件清单

| 文件 | 说明 |
|------|------|
| ~/trending-mcp/plan-final.md | 四平台完整方案 |
| ~/trending-mcp/plan.md | MCP Server 架构设计 |
| ~/trending-mcp/comparison.md | 三方案对比 |
| ~/trending-mcp/plan-this.md | 本文件（最终确认版） |

---

## 执行前提

1. ✅ 方案已确认
2. ⏳ Instagram sessionid cookie（Phase 2 需要）
3. ⏳ 用户确认开始执行

---

## 下一步

等你准备好 cookies + 确认开始，我就动手执行 Phase 1。
