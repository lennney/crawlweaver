---
type: HandoverDoc
title: crawlweaver HANDOVER
timestamp: '2026-07-20T23:35:20+08:00'
description: 会话日志和项目状态
tags:
- crawlweaver
- handoverdoc
---
# HANDOVER.md — CrawlWeaver

> 上次更新: 2026-07-20 | 历史归档: docs/history/2026-07.md

## 当前目标
迁移到 uv 包管理器 + 性能优化 + 测试门禁通过 + 飞书 Bot 端到端验证

## 进行中
- [ ] 真实飞书消息端到端验证（需用户在飞书私聊机器人发 URL）

## 待办（按优先级）
| # | 事项 | 说明 |
|---|------|------|
| 1 | **端到端确认** | 用户在飞书私聊发 URL，确认进度卡片+结果卡片出现 |
| 2 | **交互卡片按钮** | confirm_card 加确认/取消按钮 + card.action.trigger 事件订阅 |
| 3 | 自然语言 Schema 提取 | "帮我爬这个产品的：名称、价格、库存" |

## 关键决策
| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-07-19 | uv 替代 pip | Rust 实现，10x 解析速度，原生 lock 文件，pyproject.toml 原生支持 |
| 2026-07-19 | LLM 内存缓存（LRU 500）替代纯磁盘缓存 | 高频调用场景（dashboard 刷新）磁盘 I/O 成为瓶颈，μs 级内存命中消除 |
| 2026-07-19 | knowledge.json mtime 缓存替代每次读盘 | dashboard 每 5s 刷新 stats，5 个端点各读一次盘 → 统一缓存减少 5x 读盘 |
| 2026-07-03 | 建立 ADR 目录 | 记录关键架构决策，避免回看时"为什么这么写" |

## 下一步
1. 用户在飞书发消息验证 → 确认进度卡片 + 结果卡片
2. 再加交互卡片按钮（确认/取消）
3. 考虑飞书多维表格写入
