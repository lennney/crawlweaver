"""Render tool — generate HTML from article + SEO metadata.

Pure deterministic code — no LLM involved.
Uses Jinja2 templates from templates/ directory.
"""

import logging
import re
from datetime import datetime
from pathlib import Path

from state import CrawlState, Step

logger = logging.getLogger("crawler.render")

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
OUTPUT_DIR = Path(__file__).parent.parent / "output"


def render(state: CrawlState) -> CrawlState:
    """Render article to HTML file."""
    if not state.article_md:
        state.error = "No article_md to render"
        state.append_event("render", False, "No article_md")
        return state

    try:
        from jinja2 import Environment, FileSystemLoader

        # Convert markdown to HTML sections
        sections_html = _markdown_to_sections(state.article_md)
        faq_html = _extract_faq(state.article_md)

        # Try loading template, fallback to basic
        template_file = "article.html"
        if not (TEMPLATES_DIR / template_file).exists():
            template_file = None

        if template_file:
            env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False)
            template = env.get_template(template_file)
        else:
            template = _basic_template()

        html = template.render(
            title=state.seo.h1 or state.title,
            meta_description=state.seo.meta_description,
            keyword=state.keyword,
            article_md=state.article_md,
            sections_html=sections_html,
            faq_html=faq_html,
            source_url=state.url,
            source_title=state.title,
            accessed_date=datetime.now().strftime("%Y-%m-%d"),
            seo=state.seo,
        )

        # Write output
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        slug = state.seo.url_slug.strip("/").replace("/", "_") or _slugify(state.keyword or state.title)
        out_path = OUTPUT_DIR / f"{slug}.html"
        out_path.write_text(html, encoding="utf-8")

        state.html_path = str(out_path)
        state.step = Step.RENDERED
        state.append_event("render", True, f"Written to {out_path}")
        logger.info(f"Rendered: {out_path}")

    except Exception as e:
        state.error = str(e)
        state.append_event("render", False, str(e))
        logger.error(f"Render failed: {e}")

    return state


def _markdown_to_sections(md: str) -> str:
    """Convert markdown to HTML sections (H2 blocks)."""
    try:
        import markdown
        return markdown.markdown(md, extensions=["fenced_code", "tables"])
    except ImportError:
        # Fallback: basic conversion
        html = md
        html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
        html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
        html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
        html = re.sub(r"\n\n", "</p><p>", html)
        return f"<p>{html}</p>"


def _extract_faq(md: str) -> str:
    """Extract FAQ section from markdown."""
    faq_match = re.search(r"(## (?:FAQ|Frequently Asked).+?)(?=\n## (?!FAQ)|$)", md, re.DOTALL | re.IGNORECASE)
    if faq_match:
        try:
            import markdown
            return markdown.markdown(faq_match.group(1), extensions=["fenced_code"])
        except ImportError:
            return faq_match.group(1)
    return ""


def _slugify(text: str) -> str:
    """Convert text to URL slug."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:50] or "article"


def _basic_template():
    """Fallback template when no Jinja2 template file exists."""
    from jinja2 import Template
    return Template("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ title }}</title>
    <meta name="description" content="{{ meta_description }}">
</head>
<body>
    <article>
        <h1>{{ title }}</h1>
        {{ sections_html }}
        {{ faq_html }}
        <footer>
            <p>Source: <a href="{{ source_url }}">{{ source_title }}</a></p>
            <p>Accessed: {{ accessed_date }}</p>
        </footer>
    </article>
</body>
</html>""")
