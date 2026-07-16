# YouTube-to-Article — AI Agent Instructions

> Transform YouTube videos into structured DIY articles with SEO metadata and HTML.
> **Designed for AI agents to call. No manual steps needed.**

## Quick Start for AI

```bash
# 1. Install
pip install youtube-to-article

# 2. Set up .env (API key for LLM)
echo "LLM_API_KEY=sk-your-key" >> .env
echo "LLM_BASE_URL=https://api.deepseek.com" >> .env
echo "LLM_MODEL=deepseek-chat" >> .env

# 3. Export YouTube cookies from browser as Netscape-format cookies.txt
#    (Use "Get cookies.txt" Chrome extension)

# 4. Generate article
ytarticle run --url "https://www.youtube.com/watch?v=xxx" \
              --cookies cookies.txt \
              --template diyhub
```

## Pipeline Flow

```
YouTube URL
  → youtube_extract  (yt-dlp: subtitle + metadata)
  → ai_rewrite       (LLM: transcript → structured markdown)
  → youtube_frames   (yt-dlp + ffmpeg: step images)
  → seo_metadata     (LLM: title/meta/url_slug)
  → html_render      (Jinja2: template → HTML with Schema.org)
  → content_check    (quality validation)
  → Output HTML ✨
```

## CLI Usage

### Basic
```bash
ytarticle run --url "https://youtube.com/watch?v=xxx"

# With cookies (required for most YouTube videos)
ytarticle run --url "..." --cookies cookies.txt

# Custom template
ytarticle run --url "..." --template default
```

### Advanced
```bash
# Full control with custom config file
ytarticle run --url "..." --config myconfig.yaml

# Custom LLM (override .env inline)
LLM_BASE_URL=https://api.openai.com/v1 LLM_MODEL=gpt-4o \
  ytarticle run --url "..." --cookies cookies.txt

# JSON output (AI parses this)
ytarticle run --url "..." --json

# List available templates
ytarticle templates
```

## Configuration

### .env (environment variables)
| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_API_KEY` | _(required)_ | Any OpenAI-compatible API key |
| `LLM_BASE_URL` | `https://api.deepseek.com` | API endpoint |
| `LLM_MODEL` | `deepseek-chat` | Model name |
| `COOKIES_PATH` | — | Path to Netscape cookies file |
| `HTTP_PROXY` | — | HTTP proxy for yt-dlp |

### config.yaml (pipeline steps)
Override the default pipeline by creating a custom YAML:

```yaml
steps:
  - component: youtube_extract
    id: extract
    config:
      output_dir: output/raw
      cookies_path: "cookies.txt"

  - component: ai_rewrite
    id: rewrite
    config:
      prompt_file: prompts/rewrite_article.md

  - component: html_render
    id: render
    config:
      template: default/article.html
      site_name: MySite
      site_url: https://mysite.com
```

## Templates

| Name | Description |
|------|-------------|
| `diyhub` | MakeDIYHub style (Lora/DM Sans, sage green, info grid) |
| `default` | Minimal, clean, responsive |

Custom templates: create a `<name>/article.html` in `templates/` directory, 
then use `--template <name>`.

## For AI Agents

This tool is built for AI-to-AI workflows. When your AI needs to 
create content from YouTube:

1. **Get the YouTube URL** from the user
2. **Check for cookies** — ask user to export from browser if needed
3. **Set up .env** with a valid LLM API key
4. **Call the tool** with appropriate parameters
5. **Parse the JSON output** or read the generated HTML file

### Python API (for agent integration)

```python
from ytarticle.core.pipeline import Pipeline
from ytarticle.core.schema import make_item

config = {"steps": [...]}  # or load from YAML
item = make_item("youtube", "video_id", title="...", raw_text="...")
result = Pipeline(config).run(item)

print(f"HTML: {result.artifacts.html_path}")
print(f"SEO title: {result.seo.title_tag}")
```

## Required Dependencies

- **yt-dlp** — YouTube extraction (`pip install yt-dlp`)
- **ffmpeg** — frame extraction (`brew install ffmpeg` on Mac)
- **LLM API** — any OpenAI-compatible service (DeepSeek, OpenAI, etc.)
