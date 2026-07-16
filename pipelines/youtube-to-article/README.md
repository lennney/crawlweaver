# youtube-to-article

> **YouTube video → structured DIY article, fully automated.**
> yt-dlp extraction → AI rewrite → SEO metadata → HTML with Schema.org markup.

Built for **AI agents** — call it from a single CLI command, or embed it as a Python library. Produces production-ready HTML articles with structured data (HowTo, Article, FAQ, BreadcrumbList schema).

## Quick Start (for AI agents)

```bash
# 1. System dependencies
pip install yt-dlp           # YouTube extraction
brew install ffmpeg          # frame extraction (macOS)
# apt install ffmpeg          # (Linux)

# 2. Install youtube-to-article
pip install youtube-to-article

# 3. Configure LLM (any OpenAI-compatible API)
cp .env.example .env
# Edit .env — set your LLM_API_KEY

# 4. Export YouTube cookies (Netscape format)
#    Use "Get cookies.txt" Chrome extension — save as cookies.txt

# 5. Generate an article
ytarticle run --url "https://www.youtube.com/watch?v=xxx" \
              --cookies cookies.txt \
              --template diyhub

# Output: output/html/<video_id>.html
```

## Prerequisites

| Requirement | Version | Purpose |
|-------------|---------|---------|
| Python | ≥ 3.12 | Runtime |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | latest | YouTube subtitle + metadata extraction |
| ffmpeg | latest | Frame/image extraction from video |
| LLM API key | — | Article rewriting & SEO (DeepSeek, OpenAI, etc.) |

## Installation

### From PyPI

```bash
pip install youtube-to-article
```

### Dev install (editable, recommended for contributors)

```bash
git clone https://github.com/lennney/youtube-to-article.git
cd youtube-to-article

# With uv (recommended)
uv sync

# With pip
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Verify installation:

```bash
ytarticle --help
# → CLI groups: run, templates

ytarticle templates
# → default, diyhub
```

## Configuration

### `.env` file (minimum setup)

```bash
LLM_API_KEY=sk-xxx              # Required — any OpenAI-compatible key
LLM_BASE_URL=https://api.deepseek.com  # Optional (default)
LLM_MODEL=deepseek-chat                # Optional (default)
COOKIES_PATH=cookies.txt               # Optional — YouTube auth
HTTP_PROXY=http://127.0.0.1:8080       # Optional — proxy for yt-dlp
```

### Environment variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `LLM_API_KEY` | — | ✅ | Any OpenAI-compatible API key |
| `LLM_BASE_URL` | `https://api.deepseek.com` | ❌ | API endpoint |
| `LLM_MODEL` | `deepseek-chat` | ❌ | Model name |
| `COOKIES_PATH` | — | ❌ | Path to Netscape-format cookies.txt |
| `HTTP_PROXY` / `HTTPS_PROXY` | — | ❌ | Proxy for yt-dlp |

## Usage

### CLI

```bash
# Full pipeline (recommended)
ytarticle run \
  --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ" \
  --cookies cookies.txt \
  --template diyhub \
  --site-name "MakeDIYHub" \
  --site-url "https://makediyhub.com"

# Minimal (no cookies, may fail on age-restricted videos)
ytarticle run --url "https://youtu.be/xxx"

# JSON output (for AI agent parsing)
ytarticle run --url "..." --cookies cookies.txt --json
# → {"status": "done", "title": "...", "html_path": "...", "word_count": 523}

# Custom config file
ytarticle run --url "..." --config myconfig.yaml

# List available HTML templates
ytarticle templates

# Enable debug logging
ytarticle --verbose run --url "..."
```

### Python API

```python
from ytarticle.core.pipeline import Pipeline
from ytarticle.core.schema import make_item

# Create a pipeline item
item = make_item(
    source="youtube",
    source_id="dQw4w9WgXcQ",
    source_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    keyword="DIY Projects",
)

# Run with default config (YAML file)
result = Pipeline("configs/default.yaml").run(item)

# Or run with inline config
config = {
    "steps": [
        {"component": "youtube_extract", "id": "extract",
         "config": {"output_dir": "output/raw"}},
        {"component": "ai_rewrite", "id": "rewrite",
         "config": {"prompt_file": "prompts/rewrite_article.md"}},
        {"component": "youtube_frames", "id": "frames",
         "config": {"output_dir": "output/images"}},
        {"component": "seo_metadata", "id": "seo",
         "config": {"site_name": "MakeDIYHub"}},
        {"component": "html_render", "id": "render",
         "config": {"template": "diyhub/article.html",
                   "output_dir": "output/html",
                   "site_url": "https://makediyhub.com",
                   "site_name": "MakeDIYHub"}},
        {"component": "content_check", "id": "check", "config": {}},
    ]
}
result = Pipeline(config).run(item)

# Check result
if result.status == "done":
    print(f"✅ {result.artifacts.html_path}")
    print(f"   Title: {result.title}")
    print(f"   Words: {len(result.article_md.split())}")
else:
    print(f"❌ {result.error}")
```

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# With coverage
python -m pytest tests/ --cov=ytarticle -v

# Run specific test file
python -m pytest tests/test_pipeline.py -v
```

Test output example:

```
tests/test_pipeline.py::TestPipeline::test_pipeline_with_components PASSED
tests/test_pipeline.py::TestPipeline::test_pipeline_component_not_found PASSED
tests/test_pipeline.py::TestPipeline::test_pipeline_missing_input PASSED
tests/test_pipeline.py::TestPipeline::test_pipeline_yaml_config PASSED
```

## Pipeline Architecture

```
YouTube URL
  │
  ▼
┌─────────────────────┐
│ youtube_extract     │  yt-dlp → subtitle + metadata + channel info
│ (sources/)          │
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ ai_rewrite          │  LLM → transcript → structured markdown
│ (processors/)       │  (step-by-step, difficulty, materials, cost)
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ youtube_frames      │  yt-dlp + ffmpeg → step-by-step images
│ (sources/)          │
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ seo_metadata        │  LLM → title_tag, meta_description, url_slug
│ (processors/)       │  (SEO-optimized, Schema.org-ready)
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ html_render         │  Jinja2 → HTML with Schema.org structured data
│ (processors/)       │  (HowTo, Article, FAQ, BreadcrumbList)
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ content_check       │  Quality validation (word count, SEO, etc.)
│ (checkers/)         │
└─────────┬───────────┘
          ▼
      Output HTML ✨
```

Components are auto-discovered from `src/ytarticle/components/{sources,processors,checkers}/`. Each component implements the `BaseComponent` interface:

```python
from ytarticle.core.base import BaseComponent

class MyComponent(BaseComponent):
    name = "my_component"
    version = "1.0.0"
    required_fields = ["raw_text"]     # validated before run
    output_fields = ["article_md"]     # validated after run

    def run(self, item, config) -> ContentItem:
        # Transform item, return it
        return item
```

## Templates

| Name | Style | Best for |
|------|-------|----------|
| `default` | Minimal, clean, responsive | Generic tech blogs |
| `diyhub` | Lora/DM Sans, sage green, info grid, Amazon card | MakeDIYHub.com |

Create custom templates: add `<name>/article.html` under any template dir, then use `--template <name>`. Template variables are documented in `configs/default.yaml`.

## Advanced Configuration

Create a custom pipeline YAML:

```yaml
steps:
  - component: youtube_extract
    id: extract
    config:
      output_dir: output/raw
      cookies_path: cookies.txt
      proxy_http: ""               # or "http://127.0.0.1:8080"

  - component: ai_rewrite
    id: rewrite
    config:
      prompt_file: prompts/rewrite_article.md

  - component: html_render
    id: render
    config:
      template: mytemplate/article.html
      site_url: https://mysite.com
      site_name: MySite
      output_dir: output/html
```

Then run:

```bash
ytarticle run --url "..." --config myconfig.yaml
```

CLI flags (`--cookies`, `--proxy`, `--template`, etc.) automatically merge into the relevant step configs — you don't need both.

## Project Structure

```
youtube-to-article/
├── src/
│   └── ytarticle/
│       ├── cli.py                # CLI entry point (Click)
│       ├── core/
│       │   ├── schema.py         # Data contract (ContentItem)
│       │   ├── base.py           # BaseComponent interface
│       │   ├── pipeline.py       # Pipeline orchestrator
│       │   └── registry.py       # Auto-discovery of components
│       ├── components/
│       │   ├── sources/          # Data extraction (YouTube)
│       │   ├── processors/       # Transformation (AI, SEO, Render)
│       │   └── checkers/         # Quality validation
│       ├── templates/            # HTML templates (Jinja2)
│       │   ├── default/
│       │   └── diyhub/
│       └── support/              # Utilities (LLM, cookies, proxy)
├── prompts/                      # LLM prompt templates
├── configs/                      # Pipeline YAML configs
├── tests/                        # pytest test suite
├── pyproject.toml
└── .env.example
```

## For AI Agents Calling This Tool

```markdown
1. **Install** → `pip install youtube-to-article`
2. **Set up LLM** → create `.env` with `LLM_API_KEY=sk-...`
3. **Get cookies** → ask user to export cookies.txt from browser
4. **Run** → `ytarticle run --url <URL> --cookies cookies.txt`
5. **Parse output** → use `--json` flag for machine-readable results
6. **Read the article** → the HTML file path is in the JSON output
```

## License

MIT
