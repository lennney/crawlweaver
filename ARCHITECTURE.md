# AI Crawler v2 — 12-Factor Agents 重构

> 版本: v2.1
> 日期: 2026-06-07
> 原则: 12-Factor Agents (humanlayer/12-factor-agents)

## 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 控制流 | reducer.py 里的纯函数 | Factor #8: Own your control flow |
| 状态模型 | 单一 Pydantic model | Factor #5: Unify execution + business state |
| 工具接口 | 纯函数 (state) → state | Factor #4: Tools are structured outputs |
| 记忆 | Knowledge.json + 预加载 | Factor #13: Pre-fetch context |
| LLM调用 | llm.py 直接调用 | Factor #2: Own your prompts |
| 入口 | CLI/Dashboard/API 都调同一个 reducer | Factor #11: Trigger from anywhere |
| JSON 解析 | tools/parse.py 共享解析器 | Factor #4: 消除重复，集中处理 |
| 失败处理 | 结构化 failure_report | Factor #7: 失败时通知人类 |
| WAL 模式 | 每步自动 checkpoint | Factor #6: 崩溃可恢复 |
| Web 框架 | FastAPI + Jinja2 + HTMX | 轻量级，无 JS 构建步骤 |

## 目录结构

```
ai-crawler-v2/
├── ARCHITECTURE.md    # 本文件
├── state.py           # CrawlState 模型 (含 failure_report)
├── llm.py             # LLM 客户端（DeepSeek → Ollama fallback）
├── knowledge.py       # Knowledge 模型 (含 site_patterns, record_site_pattern)
├── context.py         # Context Engineering — 常量: MAX_SOURCE_CHARS, MAX_ARTICLE_CHARS, MAX_ARTICLE_PREVIEW_CHARS
├── tools/
│   ├── __init__.py
│   ├── extract.py     # YouTube/Web/Reddit 提取
│   ├── rewrite.py     # AI 改写 (使用 parse_llm_output 验证)
│   ├── seo.py         # SEO 元数据 (使用共享 parse_json)
│   ├── render.py      # HTML 渲染
│   ├── verify.py      # AI 自检 (使用共享 parse_json)
│   └── parse.py       # 共享 JSON/LLM 输出解析器
├── reducer.py         # 核心 reducer — 控制流 + WAL checkpoint
├── web/
│   ├── __init__.py
│   ├── app.py         # FastAPI 应用入口
│   ├── api.py         # REST API 路由 (jobs, knowledge, articles)
│   └── templates/
│       ├── base.html  # 基础模板 (Tailwind + HTMX)
│       └── dashboard.html  # Dashboard 主页
├── prompts/           # LLM 提示词（从 v1 保留）
├── templates/         # HTML 模板（从 v1 保留）
├── cli.py             # CLI 入口 (crawl, setup, knowledge, dashboard)
├── setup.py           # 首次运行引导
└── tests/
    ├── test_reducer.py
    ├── test_context.py
    ├── test_parse.py
    ├── test_knowledge.py
    ├── test_wal.py
    └── test_web.py
```

## API Endpoints (web/api.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | Dashboard HTML 页面 |
| GET | `/api/health` | 健康检查 `{"status": "ok"}` |
| GET | `/api/jobs` | 列出最近 50 个任务 (读 states/ 目录) |
| POST | `/api/jobs` | 提交新爬虫任务 (后台运行) |
| GET | `/api/knowledge` | 知识库统计 (knowledge.json) |
| GET | `/api/knowledge?panel=patterns` | site_patterns 表格 HTML |
| GET | `/api/articles` | 列出生成的 HTML 文章 |
| GET | `/api/articles/{name}` | 返回文章 HTML 文件 |

## 关键常量 (context.py)

```python
MAX_SOURCE_CHARS = 3000        # 原始内容截断上限
MAX_ARTICLE_CHARS = 4000       # 文章内容截断上限
MAX_ARTICLE_PREVIEW_CHARS = 2000  # 文章预览截断上限
```

## 状态模型 (state.py)

`CrawlState` 包含:
- 基本字段: url, source, keyword, content_type, target_words
- Pipeline 字段: raw_text, article_md, seo, html_path, verify
- **failure_report** (dict|None): 失败时自动填充，含 url/error/step/attempts
- events: 事件时间线

## Knowledge 模型 (knowledge.py)

`Knowledge` 包含:
- crawled_urls: 已爬取 URL 集合
- **site_patterns**: 域名 → SitePattern 映射
  - SitePattern: extractor, best_prompt, avg_quality, sample_count, total_quality
  - **record_site_pattern()**: 自动计算移动平均
- failure_log: 失败记录列表
- prompt_stats: 提示词性能统计

## Reducer WAL 模式 (reducer.py)

`crawl(state, knowledge, llm, state_path=None)` 在每步完成后自动写 state.json:
- extract → checkpoint
- rewrite → checkpoint
- seo → checkpoint
- render → checkpoint
- verify → checkpoint

进程崩溃后可从最近的 checkpoint 恢复。

## 共享解析器 (tools/parse.py)

- `parse_json(text)`: 从 LLM 响应中提取 JSON (3 种策略)
- `parse_llm_output(text, min_length)`: 验证 LLM 文本输出 (去 <think> 标签)

## 12-Factor 映射

| # | Factor | 实现位置 |
|---|--------|---------|
| 1 | NL → Tool Calls | tools/rewrite.py, tools/seo.py, tools/verify.py 内部调 LLM |
| 2 | Own Prompts | prompts/ 目录，每个 tool 自己加载 |
| 3 | Own Context | context.py — 常量定义 + 代码决定 LLM 看到什么 |
| 4 | Tools = Structured Output | tools/parse.py 共享解析，每个 tool 构造→调用→解析→更新 |
| 5 | Unify State | state.py — CrawlState 含 execution + business state + failure_report |
| 6 | Launch/Pause/Resume | WAL 模式: reducer 每步自动 checkpoint，支持崩溃恢复 |
| 7 | Contact Humans | failure_report 结构化通知 + CLI 输出失败报告 |
| 8 | Own Control Flow | reducer.py — if/else/for，没有黑盒 |
| 9 | Compact Errors | verify 失败 → 错误压缩 → 塞回 context → 重试 |
| 10 | Small Focused Agents | 每个 tool 只做一件事 |
| 11 | Trigger Anywhere | cli.py (crawl/dashboard) + web/api.py (POST /api/jobs) |
| 12 | Stateless Reducer | reducer.crawl(state, knowledge, llm) → state |
| 13 | Pre-fetch + Site Patterns | knowledge.py 加载 + record_site_pattern 积累域名模式 |
