# 项目文档索引

> Agent 自动生成的文档导航。列出所有可用文档及其读取时机。

## 总是加载

| 文件 | 内容 | 读取时机 |
|------|------|---------|
| `AGENTS.md` | 技术栈、命令、约束 | session 启动自动加载 |
| `docs/index.md` | 本文件，文档导航 | 首次进入 docs/ 时 |

## 按需加载

| 文件 | 内容 | 读取时机 |
|------|------|---------|
| `docs/active_plan.md` | 当前任务拆解 | 开始新任务时 |
| `docs/architecture.md` | 架构设计 | 涉及模块拆解时 |
| `docs/conventions.md` | 编码规范 | 新增文件时 |
| `docs/deployment.md` | 部署流程 | 上线前 |
| `docs/troubleshooting.md` | 已知问题诊断 | 遇到报错时 |
| `docs/known_issues.md` | 已知 bug 和方案 | 遇到异常行为时 |
| `docs/decisions/` | 架构决策记录 | 涉及架构变更时 |

## 会话记录

| 文件 | 内容 | 读取时机 |
|------|------|---------|
| `HANDOVER.md` | 会话日志+变更记录 | 每次 session 开始 |
| `docs/history/` | 归档会话记录 | 需要回溯时 |
