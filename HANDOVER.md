# HANDOVER.md — CrawlWeaver

> 上次更新: 2026-06-28 14:15 CST

## 当前目标
飞书 Bot 打通：非技术同事在飞书贴 URL → Bot 自动爬取 → AI 生成 → 卡片返回结果

## 已完成

### Core Pipeline
- [x] CrawlWeaver 后端部署（systemd, :8090, 开机自启）
- [x] LLM 推理兼容修复 — `extra_body={"thinking": {"type": "disabled"}}` 关闭推理
- [x] 全管线通过：extract → rewrite → seo → render → verify
- [x] max_tokens 调优：rewrite 4096→8192, seo 512→2048, verify 1024→4096
- [x] 空内容重试逻辑 — 推理模型内容为空时自动翻倍 token 重试
- [x] parse_llm_output 兼容 `<think>` 和 `Thinking. N.` 两种格式

### Feishu Integration (2026-06-28)
- [x] 飞书 Bot 模块 — bot/feishu.py + cards.py + url_parser.py
- [x] Cloudflare Tunnel 建好 — `crawl.take-a-deep-breath0.com` → :8090
- [x] SDK 事件分发 — lark-oapi EventDispatcherHandler 自动验签/路由
- [x] Webhook 签名验证 — FEISHU_VERIFICATION_TOKEN 校验
- [x] 消息解析修复 — `message.content` 直接字段（不是 `body.content`）
- [x] 全链路自测通过 — 模拟消息事件 → SDK 处理 → 爬取 → 结果卡片
- [x] 项目文档更新 — AGENTS.md / ARCHITECTURE.md / .env.example

## 进行中
- [ ] 真实飞书消息端到端验证（需用户在飞书私聊机器人发 URL）

## 待办（按优先级）

| # | 事项 | 说明 |
|---|------|------|
| 1 | **端到端确认** | 用户在飞书私聊发 URL，确认进度卡片+结果卡片出现 |
| 2 | **交互卡片按钮** | confirm_card 加确认/取消按钮 + card.action.trigger 事件订阅 |
| 3 | 自然语言 Schema 提取 | "帮我爬这个产品的：名称、价格、库存" |
| 4 | 飞书多维表格写入 | 结果直接入库 |
| 5 | 飞书 Cron 面板 | 定时任务 Web UI |
| 6 | MCP Server 暴露 | Hermes agent 直接调 CrawlWeaver |

## 关键决策

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-06-28 | Cloudflare Tunnel 替代公网 IP | VM 无公网 IPv4，用 tunnel 最省事 |
| 2026-06-28 | 回调地址模式，非长连接 | 已建好隧道，Webhook 比 WebSocket 守护进程简单 |
| 2026-06-28 | lark-oapi SDK 处理事件 | 官方 SDK 自动处理验签/解密/事件分发，比自己手写稳 |
| 2026-06-28 | 跳过确认卡片，直接爬取 | 用户发 URL 本身就是意图，去掉点击确认的摩擦 |
| 2026-06-28 | reply_to 发卡片 | 用用户消息的 message_id 回复，保持对话上下文 |
| 2026-06-28 | deepseek-v4-flash + thinking=disabled | 推理模型空输出根因，一行修复 |

## 已尝试且失败的方法

- ❌ HMAC 手写验签 — 飞书回调用 token+header 双重校验，SDK 更可靠
- ❌ 长连接模式 — 选错了飞书订阅方式，应选"回调地址"
- ❌ `message.body.content` 解析 — SDK 模型里 content 是直接字段
- ❌ systemd `EnvironmentFile` — 部分系统不生效，改用 `Environment=` 直写

## 环境变量 (systemd)

```
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_VERIFICATION_TOKEN=xxx
DEEPSEEK_API_KEY=xxx              # OpenCode Go key
LLM_BASE_URL=https://opencode.ai/zen/go/v1
LLM_MODEL=deepseek-v4-flash
```

## 运行状态

```
CrawlWeaver API    ✅ :8090 (systemd, active)
Cloudflare Tunnel  ✅ crawl.take-a-deep-breath0.com → :8090
LibreCrawl MCP     ✅ :5080 (systemd)
LLM (deepseek-v4)  ✅ thinking=disabled
飞书 Bot 模块       ✅ lark-oapi SDK webhook
飞书开放平台        ✅ 回调地址已配 + 已发布版本
```

## 下一步
1. 用户在飞书发消息验证 → 确认进度卡片 + 结果卡片
2. 再加交互卡片按钮（确认/取消）
3. 考虑飞书多维表格写入
