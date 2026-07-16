# 🕷️ CrawlWeaver

**AI 内容工厂 — 多源爬取 × SEO 改写 × 知识自进化**

> 输入 URL，输出 SEO 文章。用得越多，爬得越准。
> 6 大内容源自动识别 · 6 步全自动流水线 · 域名策略记忆 · 知识持续积累

[![Tests](https://img.shields.io/badge/tests-109-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![12-Factor](https://img.shields.io/badge/12--Factor%20Agents-✓-brightgreen)](https://github.com/humanlayer/12-factor-agents)

---

## 为什么做这个项目

内容运营的日常：从 YouTube / Reddit / 知乎手动采集素材 → 花 2-4 小时改写一篇 SEO 文章 → 换个域名又要从头踩坑。

CrawlWeaver 把这条链路自动化：

```
URL 进 → 内容提取 → AI 改写 → SEO 元数据 → HTML 渲染 → AI 自检
                                                    ↓ 不合格
                                                自动修复（最多 2 次）
                                                    ↓ 仍不合格
                                                进入人工审核队列
```

**核心差异化：知识自进化** — 同一域名爬 3 次后，系统自动选择历史上表现最好的提取器和 Prompt。用得越多，成功率越高。

---

## 支持的内容源

| 来源 | URL 示例 | 提取方式 |
|------|----------|----------|
| 🎬 YouTube | `youtube.com/watch?v=...` | 字幕 API → yt-dlp 兜底 |
| 🌐 Web | 任意 URL | requests + BeautifulSoup |
| 💬 Reddit | `reddit.com/r/.../comments/...` | JSON API |
| 🐦 Twitter/X | `twitter.com/.../status/...` | oembed → 爬取兜底 |
| 📱 微信公众号 | `mp.weixin.qq.com/s/...` | 服务端 HTML 提取 |
| 📖 知乎 | `zhuanlan.zhihu.com/p/...` | 文章/回答 API → 爬取兜底 |

来源类型从 URL 自动识别，无需手动指定。

---

## 30 秒上手

```bash
git clone https://github.com/lennney/crawlweaver.git && cd crawlweaver

pip install -r requirements.txt     # 安装依赖
export DEEPSEEK_API_KEY="***"       # 配置 LLM

python cli.py crawl "https://example.com/article" --keyword "目标关键词"
python cli.py dashboard --port 8080  # 启动 Dashboard
```

---

## 架构（12-Factor Agents）

```
┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Extract │ → │ Rewrite  │ → │   SEO    │ → │  Render  │ → │  Verify  │ → │ Publish  │
│ 内容提取 │    │  AI 改写  │    │ 元数据   │    │ HTML 渲染 │    │  AI 自检  │    │  发布    │
└─────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
                                    ↑                                        ↓ 不通过
                              Knowledge DB                              Fix（最多 2 次）
                           (域名策略 + Prompt 性能)                          ↓ 仍不通过
                                                                     人工审核队列
```

整个流水线是 `reducer.py` 里的一个纯函数。状态是单一 Pydantic model。工具是无状态函数。这是 [12-Factor Agents](https://github.com/humanlayer/12-factor-agents) 的核心原则。

| 12-Factor 原则 | CrawlWeaver 实现 |
|----------------|-----------------|
| #2 Own your prompts | `llm.py` 直接管理所有 Prompt |
| #4 Tools are structured outputs | `tools/` 下每个模块都是纯函数 |
| #5 Unify state | 单一 `CrawlState` Pydantic model |
| #6 Crash recovery | WAL 模式，每步自动 checkpoint |
| #7 Notify humans on failure | 结构化 `failure_report` |
| #8 Own your control flow | `reducer.py` 纯函数控制全流程 |
| #11 Trigger from anywhere | CLI / Dashboard / API 都调同一个 reducer |
| #13 Pre-fetch context | Knowledge.json 预加载域名策略 |

---

## CLI 命令

```bash
python cli.py crawl <url>           # 爬取单个 URL
python cli.py batch <csv>           # CSV 批量导入
python cli.py cron --config cron.yaml  # 定时爬取
python cli.py knowledge --show      # 查看知识库统计
python cli.py dashboard             # 启动 Web Dashboard
python cli.py publish               # 生成静态站（含 RSS）
python cli.py setup                 # 首次运行引导
```

---

## Dashboard（9 面板）

FastAPI + HTMX 实现，无 JS 构建步骤：

- 📊 任务队列监控 — 实时状态和进度
- 📈 质量趋势图 — 历史文章质量评分
- 💰 成本追踪 — LLM token 用量和费用
- 🔍 关键词覆盖率 — SEO 关键词矩阵
- 📚 知识库统计 — 域名策略和 Prompt 性能
- 🌐 站点模式表 — 各域名最佳提取器

---

## 知识自进化系统

这是 CrawlWeaver 区别于普通爬虫的核心：

| 机制 | 触发条件 | 效果 |
|------|----------|------|
| 域名策略记忆 | 同域名 3+ 次成功爬取 | 自动选择最佳提取器 + Prompt |
| 失败模式规避 | 同 URL 3+ 次失败 | 自动跳过，避免浪费算力 |
| Prompt 性能追踪 | 每次爬取后记录质量评分 | 自动优选高分 Prompt |

```
首次爬取 example.com → 成功率 ~70%
3 次爬取后 → 记住最佳策略
5 次爬取后 → 成功率 95%+
```

---

## 部署

```bash
# Docker 一键部署
docker compose up -d

# 或手动部署
bash scripts/deploy.sh --port 8080

# 定时任务（每 6 小时）
0 */6 * * * cd /path/to/crawlweaver && python cli.py cron >> /var/log/crawler.log 2>&1
```

---

## 参与贡献

欢迎 PR！适合入门的方向：

- 📝 **新内容源** — 添加 TikTok、Instagram、B站等提取器
- 🧪 **测试** — 提取器和 SEO 模块的边界 case
- 🔧 **Prompt 优化** — 改进改写和自检的 Prompt 质量
- 🌐 **国际化** — Dashboard 多语言支持

---

## License

MIT

