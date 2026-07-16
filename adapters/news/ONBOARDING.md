# 每日新闻聚合器 — 接入指引

请按以下步骤操作：

## Step 1: 克隆仓库

```bash
git clone https://github.com/lennney/news_crawler.git
cd news_crawler
```

## Step 2: 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

## Step 3: 了解你的角色

这个项目是一个**新闻爬虫框架**。你是大脑，它做机械工作。

你的工作流：
1. 我告诉你我要爬哪些新闻站
2. 你去抓取每个站点的 HTML，分析页面结构，找出 CSS selectors
3. 你把这些 selectors 写入 `data/knowledge.json`（用 `Knowledge.record_selectors()`）
4. 你把站点配置写入 `crawler/sources.py`
5. 你运行 `python crawler.py` → 机械提取 → 产出 `data/news.json`
6. 你从 `news.json` 读数据给我看

**不需要配任何 API key。** 你替代外部 LLM 的角色，你直接分析 HTML。

## Step 4: 正式开始

现在问我："你想爬哪些新闻站？"

把站点名称和网址给我就行。

---

### 关键文件说明

| 文件 | 你的操作 |
|------|---------|
| `crawler/sources.py` | 你写入站点列表 |
| `data/knowledge.json` | 你通过 `Knowledge.record_selectors()` 写入 selectors |
| `data/news.json` | 爬虫产出，你从这里读数据 |
| `AGENTS.md` | 完整架构说明，有疑问可以读