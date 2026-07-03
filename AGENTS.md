# CrawlWeaver — Agent Instructions

> 自进化 AI 爬虫：URL → 提取 → AI 改写 → SEO 优化 → 渲染 HTML → 自检评分

## 技术栈
- **Language**: Python 3.12
- **Framework**: FastAPI + uvicorn (API), HTMX (Dashboard)
- **LLM**: OpenCode Go → deepseek-v4-flash（默认），Ollama qwen2.5:7b（降级）
- **Extraction**: BeautifulSoup4 + lxml，6 来源自动识别
- **Storage**: JSON state files + LLM response cache
- **Bot**: lark-oapi SDK (飞书 Webhook 模式)
- **Package**: pip（venv）

## 常用命令
```bash
# 启动服务
systemctl --user start crawlweaver    # → http://localhost:8090

# 提交爬取任务（API）
curl -X POST http://localhost:8090/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","source":"web","keyword":"topic"}'

# 查看任务状态
curl http://localhost:8090/api/jobs/<job_id>

# 直接测试管线（CLI）
cd ~/crawlweaver && .venv/bin/python cli.py crawl \
  --url "https://example.com" --keyword "topic" --source web

# 查看日志
journalctl --user -u crawlweaver --no-pager -n 50

# 清缓存重测
rm -rf cache/llm/ __pycache__/ states/
systemctl --user restart crawlweaver

# 诊断飞书集成
cd ~/crawlweaver && .venv/bin/python debug_feishu.py check
```

## 架构
```
reducer.py（纯函数控制流）
  ├── extract()   → 6 source auto-detect (YouTube/Web/Reddit/Twitter/WeChat/Zhihu)
  ├── rewrite()   → AI 改写 (LLM)
  ├── seo()       → SEO metadata 生成
  ├── render()    → HTML 渲染 (Jinja2)
  └── verify()    → 质量自检 (评分 0-100)

bot/                          ← 飞书集成（2026-06-28 新增）
  ├── feishu.py              # Webhook 处理器 + SDK 事件分发 + trigger_crawl
  ├── cards.py               # 飞书交互卡片 JSON 模板
  └── url_parser.py          # URL 智能解析 (80% rules + 20% LLM)

web/                          ← DashBoard
  ├── app.py                 # FastAPI 应用入口（挂载 feishu router）
  └── api.py                 # REST API + HTMX 端点
```

## 飞书集成细节

### 架构
```
用户飞书发 URL
      ↓
飞书服务器 → POST /feishu/webhook → FastAPI
      ↓
lark-oapi SDK 自动处理: 验签 → token 校验 → 事件路由
      ↓
on_message → handle_message → trigger_crawl
      ↓
① 提交 CrawlWeaver API 任务
② reply_card 回复进度卡片 📦
③ 轮询任务完成
④ reply_card 回复结果卡片 ✅
```

### 环境变量
| 变量 | 来源 |
|------|------|
| `FEISHU_APP_ID` | 飞书开放平台 → 凭证与基础信息 |
| `FEISHU_APP_SECRET` | 同上 |
| `FEISHU_VERIFICATION_TOKEN` | 飞书开放平台 → 事件与回调 |
| `FEISHU_ENCRYPT_KEY` | (可选) 加密回调时使用 |

### 网络拓扑
```
Cloudflare Tunnel → crawl.take-a-deep-breath0.com → localhost:8090
                                              ↓
                                     /feishu/webhook 路由
```

### 依赖
- `lark-oapi` — 飞书官方 Python SDK (事件验签/分发)
- `lark-oapi` 自带 websockets (长连接) / aiohttp (webhook) 支持

## 关键约束
1. **API key 不硬编码** — 从 `.env` 或 systemd `Environment=` 读取
2. **不动 reducer.py** — 核心管线稳定，只加外围
3. **LLM 推理必须关闭** — `extra_body={"thinking": {"type": "disabled"}}`
4. **不跳过自检** — verify 步骤不可 skip
5. **状态文件保留** — states/ 目录不可自动清理
6. **缓存独立** — cache/llm/ 独立于代码，可随时清

## 边界
- ✅ **Always**: 加新 source/tool、修 LLM 兼容、更新 prompt、飞书集成
- ⚠️ **Ask first**: 改 reducer.py、改 state schema、加依赖
- 🚫 **Never**: 硬编码密钥、跳过 verify、删原始状态文件

## 已知陷阱
- **推理模型空输出**: deepseek-v4-flash 会把 token 全花在 thinking → `extra_body={"thinking": {"type": "disabled"}}` 关闭推理
- **LLM 缓存干扰**: 改 prompt 后不清缓存会有旧结果 → `rm -rf cache/llm/`
- **EnvironmentFile 不生效**: systemd 的 EnvironmentFile 有时不加载 → 直接用 `Environment=` 写在 service 里
- **飞书回调模式**: 必须选「回调地址」而非「长连接」，否则事件不会走 webhook
- **飞书发布版本**: 每次改事件/权限后要重新创建版本发布，否则不生效
- **飞书 SDK 消息模型**: `message.content` 是直接字段(str)，不是 `message.body.content`
- **URL 已爬过被跳过**: task_queue 会跳过已爬 URL → 用不同 URL 或清 cache
