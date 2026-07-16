# HANDOVER

> 会话日志 + 变更记录。每次 session 结束更新，新 session 开始先读。
>
> **归档规则**：超过 80 行时，旧记录移到 docs/history/YYYY-MM.md

## 当前目标
爬虫核心链路跑通，下一步：前端卡片页面。

## 变更记录

| 日期 | 类型 | 范围 | 描述 |
|------|------|------|------|
| 2026-06-29 | Added | 项目 | 初始化 workspace 架构（AGENTS.md + HANDOVER.md + docs/） |
| 2026-06-29 | Added | 爬虫 | LLM 站点发现 + 知识进化 + Scrapling 反爬集成 |

## 已完成
- [x] 2026-06-29 初始化项目结构
- [x] 2026-06-29 `crawler/llm.py` — himodels.ai API 封装，HTML 进 → selectors 出
- [x] 2026-06-29 `crawler/extractor.py` — 自适应提取（requests → Scrapling fallback）+ 质量评分 + 自动修正
- [x] 2026-06-29 `crawler/knowledge.py` — 站点策略进化（3 次成功 → 跳过 LLM）
- [x] 2026-06-29 `crawler/sources.py` — 站点注册表
- [x] 2026-06-29 OddityCentral 稳定运行（100% fill rate，零 LLM 调用）
- [x] 2026-06-29 Philstar Cloudflare Turnstile 绕过（84% fill rate，日期从 URL 提取）

## 进行中
- [ ] 2026-06-29 搭建前端卡片页面

## 待办
- [ ] 添加更多无防护/低防护新闻站点
- [ ] Philstar 摘要提取优化（carousel 页面无止摘要元素，需爬文章详情页）
- [ ] Mirror.co.uk — 需要 UK 代理（CloudFront Geo-block，非纯反爬）
- [ ] 定时爬取调度（cron / schedule）
- [ ] 分类/tags（等数据量上来后批量打标签）

## 关键决策
| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-06-29 | JSON 文件存储，不用数据库 | MVP 阶段数据量小，零运维成本 |
| 2026-06-29 | LLM 只分析 selectors，BeautifulSoup 提取 | 避免 LLM 幻觉产生错误数据；LLM token 省 90% |
| 2026-06-29 | Scrapling StealthyFetcher 替代 Playwright 裸用 | 开箱即用 Cloudflare 绕过，Chrome 指纹伪装 |
| 2026-06-29 | URL 日期提取作为 selectors 日期失败时的 fallback | Philstar carousel 卡片无日期元素，但 URL path 里带 `/YYYY/MM/DD/` |
| 2026-06-29 | knowledge.json 手动修正 OddityCentral selectors 后锁定 | LLM 第二次返回了错误 selectors（`"title": "img"`），人工修正后缓存生效 |

## 失败尝试
- ❌ `curl_cffi` TLS 指纹伪装 — 对 CloudFront/Cloudflare JS Challenge 无效
- ❌ LLM 直接返回 articles（第一版设计） — HTML 太长被截断，articles 数组为空；改为只返回 selectors
- ❌ Mirror.co.uk 直连 — CloudFront 403，非反爬而是 Geo-block，awaiting UK proxy

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 简单站点 HTTP | `requests` | 无防护站点（OddityCentral） |
| 反爬站点 HTTP | `scrapling.StealthyFetcher` | Cloudflare Turnstile 自动绕过（Philstar） |
| HTML 解析 | `beautifulsoup4` | CSS selectors 提取 |
| LLM | `himodels.ai` (deepseek-v4-flash) | 仅首次分析 HTML 结构找 selectors |
| 知识进化 | `knowledge.json` | selectors 缓存 + 成功率追踪 + 失败禁用 |

## 运行

```bash
cd news
cp .env.example .env  # 填 DEEPSEEK_API_KEY
pip install -r requirements.txt
playwright install chromium
python crawler.py
```

## 上次更新
2026-06-29
