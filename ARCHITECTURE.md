# AI Crawler v2 — 12-Factor Agents 重构

> 版本: v2.0
> 日期: 2026-06-05
> 原则: 12-Factor Agents (humanlayer/12-factor-agents)

## 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 控制流 | reducer.py 里的纯函数 | Factor #8: Own your control flow |
| 状态模型 | 单一 Pydantic model | Factor #5: Unify execution + business state |
| 工具接口 | 纯函数 (state) → state | Factor #4: Tools are structured outputs |
| 记忆 | Knowledge.json + 预加载 | Factor #13: Pre-fetch context |
| LLM调用 | llm.py 直接调用 | Factor #2: Own your prompts |
| 入口 | CLI/API/cron 都调同一个 reducer | Factor #11: Trigger from anywhere |

## 目录结构

```
ai-crawler-v2/
├── ARCHITECTURE.md    # 本文件
├── state.py           # CrawlState + Knowledge 模型
├── llm.py             # LLM 客户端（DeepSeek → Ollama fallback）
├── knowledge.py       # 跨会话知识加载/保存
├── context.py         # Context Engineering — 决定 LLM 看到什么
├── tools/
│   ├── __init__.py
│   ├── extract.py     # YouTube/Web/Reddit 提取
│   ├── rewrite.py     # AI 改写
│   ├── seo.py         # SEO 元数据
│   ├── render.py      # HTML 渲染
│   └── verify.py      # AI 自检
├── reducer.py         # 核心 reducer — 控制流在这里
├── prompts/           # LLM 提示词（从 v1 保留）
├── templates/         # HTML 模板（从 v1 保留）
├── cli.py             # CLI 入口
└── tests/
    └── test_reducer.py
```

## 12-Factor 映射

| # | Factor | 实现位置 |
|---|--------|---------|
| 1 | NL → Tool Calls | tools/rewrite.py, tools/seo.py, tools/verify.py 内部调 LLM |
| 2 | Own Prompts | prompts/ 目录，每个 tool 自己加载 |
| 3 | Own Context | context.py — 代码决定 LLM 看到什么 |
| 4 | Tools = Structured Output | 每个 tool: 构造 prompt → 调 LLM → 解析 JSON → 更新 state |
| 5 | Unify State | state.py — CrawlState 含 execution + business state |
| 6 | Launch/Pause/Resume | state.json 序列化，随时存/恢复 |
| 7 | Contact Humans | reducer.py 里的 ask_human 逻辑 |
| 8 | Own Control Flow | reducer.py — if/else/for，没有黑盒 |
| 9 | Compact Errors | verify 失败 → 错误压缩 → 塞回 context → 重试 |
| 10 | Small Focused Agents | 每个 tool 只做一件事 |
| 11 | Trigger Anywhere | cli.py 入口，调 reducer.crawl(state) |
| 12 | Stateless Reducer | reducer.crawl(state, knowledge, llm) → state |
| 13 | Pre-fetch | knowledge.py 在 reducer 启动时加载 |
