# Agent — 每日新闻聚合器

一句话：多源新闻爬虫 + 前端卡片展示，个人每日新闻阅读工具。

## 命令

```bash
# 爬取所有站点（首次 LLM 发现 selectors，后续跳过 LLM）
cd news && python crawler.py

# 查看知识进化状态
python crawler.py --stats

# 安装依赖（首次）
pip install -r requirements.txt
playwright install chromium
```

## 架构

```
_smart_fetch(url)
  ├─ requests.get()           # 快速路径（无防护站点）
  └─ StealthyFetcher          # Cloudflare Turnstile 绕过（反爬站点）

HTML → LLM/缓存 selectors → BeautifulSoup 提取 → news.json
         ↑                      ↑
    首次：LLM 发现          后续：缓存命中
         ↓                      ↓
    存 knowledge.json      零 LLM 成本
```

## 技术栈

- 爬虫：Python 3.12
- HTTP：`requests`（无防护）/ `scrapling.StealthyFetcher`（Cloudflare 绕过）
- HTML 解析：`beautifulsoup4` + CSS selectors
- LLM：himodels.ai `deepseek-v4-flash`（仅首次站点分析用）
- 前端：纯 HTML/CSS/JS（卡片式布局，待搭建）
- 数据：JSON 文件存储（`data/news.json`）

## 数据模型

```json
{
  "id": "sha256(url)",
  "title": "",
  "url": "",
  "source": "",
  "summary": "",
  "published_date": "2026-06-29",
  "cover_image": "https://...",
  "crawled_at": "2026-06-29T...",
  "site_url": "example.com"
}
```

## 已接入站点

| 站点 | 反爬 | Fill Rate | 备注 |
|------|------|-----------|------|
| OddityCentral | 无 | 100% | WordPress 站，selectors 已锁定 |
| Philstar | Cloudflare Turnstile | 84% | 日期从 URL 提取，摘要需文章详情页 |

## 约束（按优先级）

1. LLM 只用于分析 HTML 结构（找 selectors），不做数据提取
2. knowledge.json 缓存 selectors，3 次成功 → 永久跳过 LLM
3. 同站点连续失败 3 次 → 自动禁用
4. 数据存 JSON，每次爬取增量追加，URL hash 去重
5. Scrapling 仅在 requests 返回 403/blocked 时才启动（省资源）

## 边界

- ✅ **Always:** 更新 HANDOVER.md、去重用 url hash
- ⚠️ **Ask:** 换 LLM 模型、加 Playwright 直连站点、改 knowledge 进化策略
- 🚫 **Never:** 硬编码 API key、跳过 robots.txt（暂未实现但预设规则）

## 陷阱（症状 → 原因 → 解决）

- **LLM 返回空 articles** → HTML 被截断到 8000 字符，文章卡片在尾部 → 改为只让 LLM 返回 selectors（已修复）
- **LLM 第二次给出错误 selectors** → 模型不稳定，返回 `"title": "img"` → 手动修正 knowledge.json 后锁定（已处理）
- **CloudFront 403** → Geo-block 非反爬 → 需要对应地区代理，非代码问题
- **Scrapling 首次 CF challenge 超时** → Turnstile 需要 3-15s 计算 → `timeout=60` 够用

## 按需文档

- 架构: `docs/architecture.md`
- 决策: `docs/decisions/`
- 踩坑: `LEARNINGS.md`
- 会话日志: `HANDOVER.md`
