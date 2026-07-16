# 每日新闻聚合器

多源新闻爬虫框架。**AI 驱动，零外部 LLM 依赖。**

你的 AI agent 做分析（看 HTML 结构找 selectors），本项目做机械提取（BeautifulSoup + 去重 + 反爬降级）。

## 快速开始

```bash
cd news
pip install -r requirements.txt
playwright install chromium     # 反爬站点需要
```

**不需要配 API key。** 消费方 AI 自己分析 HTML，自己写 selectors。

## 工作流

```
你（消费方 AI）:
  ┌─ 收到用户需求 → 抓取目标站点 HTML
  ├─ 分析页面结构 → 确定 CSS selectors
  ├─ 写 sources.py + 写 knowledge.json
  └─ 运行 python crawler.py

crawler.py（机械层）:
  ┌─ 读 knowledge.json selectors
  ├─ 用 BeautifulSoup 提取文章
  ├─ URL hash 去重，增量追加
  └─ 产出 data/news.json
```

## 产出

`data/news.json` — 所有已抓取文章的 JSON 数组，SHA256(url) 去重，增量追加。

## 命令

| 命令 | 说明 |
|------|------|
| `python crawler.py` | 爬取所有站点，合并到 news.json |
| `python crawler.py --stats` | 查看知识进化状态 |

## 数据模型

```json
{
  "id": "sha256(url)[:16]",
  "title": "文章标题",
  "url": "https://...",
  "source": "站点名",
  "summary": "摘要",
  "published_date": "2026-06-29",
  "cover_image": "https://...",
  "crawled_at": "2026-06-29T17:54:27",
  "site_url": "www.example.com"
}
```

## 集成指南（给消费方 AI 的）

完整的 step-by-step 集成流程见 [`AGENTS.md`](./AGENTS.md)。

核心思路：你填 `sources.py` + 你写 `knowledge.json`（selectors）→ 然后 `python crawler.py` 做机械提取。

## 了解更多

- [AI 手册](AGENTS.md) — 给 AI/agent 的完整接入文档（含代码示例）
- [架构](docs/architecture.md)
- [踩坑记录](HANDOVER.md)