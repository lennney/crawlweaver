# CrawlWeaver

> 12-Factor AI Agent for content extraction, SEO article generation, and knowledge self-evolution.

[![Tests](https://img.shields.io/badge/tests-90%20passed-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.11+-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

## What is this?

A CLI + web dashboard that crawls content from multiple sources, rewrites it into SEO-optimized articles using LLM (DeepSeek → Ollama fallback), and self-improves through knowledge accumulation.

Built following [12-Factor Agents](https://github.com/humanlayer/12-factor-agents) principles — the reducer IS the control flow, tools are pure functions, state is unified.

## Features

- **Multi-source extraction**: YouTube, Web, Reddit, Twitter/X, WeChat, Zhihu
- **Knowledge self-evolution**: Auto-selects best extractor/prompt per domain after 3+ samples; skips URLs that repeatedly fail
- **SEO article generation**: LLM-powered rewrite → SEO metadata → HTML render → AI self-verification with fix loop
- **Human review queue**: Articles go through review before publishing
- **Web dashboard**: FastAPI + HTMX, 9-panel dashboard with quality trends, cost tracking, keyword coverage
- **Batch processing**: CSV import with concurrent task queue
- **Static site publisher**: Generate a full site from reviewed articles with RSS feed
- **Deployment ready**: Dockerfile + docker-compose + one-click deploy script + cron CLI

## Quick Start

```bash
# Clone
git clone https://github.com/lennney/crawlweaver.git
cd crawlweaver

# Install deps
pip install -r requirements.txt

# Set up LLM (DeepSeek recommended)
export DEEPSEEK_API_KEY="your-key"

# Crawl a URL
python cli.py crawl "https://example.com/article" --source web --keyword "target keyword"

# Launch dashboard
python cli.py dashboard --port 8080
```

## Supported Sources

| Source | URL Pattern | Method |
|--------|-------------|--------|
| YouTube | `youtube.com/watch?v=...` | Transcript API → yt-dlp fallback |
| Web | Any URL | requests + BeautifulSoup |
| Reddit | `reddit.com/r/.../comments/...` | JSON API |
| Twitter/X | `twitter.com/.../status/...` | oembed API → scraping fallback |
| WeChat | `mp.weixin.qq.com/s/...` | Server-side HTML extraction |
| Zhihu | `zhuanlan.zhihu.com/p/...` | Article/Answer API → scraping fallback |

Source type is auto-detected from URL — no need to specify `--source` manually.

## CLI Commands

```bash
python cli.py crawl <url>          # Crawl a single URL
python cli.py batch <csv>           # Batch import from CSV
python cli.py cron --config cron_config.yaml  # Run scheduled crawl
python cli.py cron --dry-run        # Preview cron jobs
python cli.py knowledge --show      # View knowledge summary
python cli.py dashboard             # Launch web dashboard
python cli.py publish               # Generate static site
python cli.py setup                 # First-run YouTube cookies setup
```

## Architecture

```
URL → extract → rewrite → seo → render → verify
                                           | fail
                                       fix (max 2x)
                                           | still fail
                                       mark for human review
```

The entire flow is one pure function in `reducer.py`. State is a single Pydantic model. Tools are stateless functions. This is the point.

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design decisions.

## Docker Deployment

```bash
# Build and run
docker compose up -d

# Or one-click deploy
bash scripts/deploy.sh --port 8080
```

## Cron Jobs

```yaml
# cron_config.yaml
jobs:
  - url: "https://example.com/article"
    keyword: "target keyword"
    # source: auto-detected from URL
```

```bash
# System cron: every 6 hours
0 */6 * * * cd /path/to/ai-crawler-v2 && python cli.py cron >> /var/log/crawler.log 2>&1
```

## Knowledge Self-Evolution

The crawler learns from experience:

- **Site patterns**: After 3+ successful crawls on a domain, automatically uses the best-performing extractor and prompt
- **Failure avoidance**: URLs that fail 3+ times are auto-skipped
- **Quality tracking**: Records per-prompt average scores, picks the best for each source type

## License

MIT
