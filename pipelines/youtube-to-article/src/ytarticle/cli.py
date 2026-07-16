"""CLI — Complete YouTube-to-article pipeline with batch and export support."""
from __future__ import annotations
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import click

from ytarticle.core.schema import make_item
from ytarticle.core.pipeline import Pipeline


@click.group()
@click.option("--verbose", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx, verbose: bool):
    """youtube-to-article — YouTube video → structured DIY article.

    Full pipeline: extract → rewrite → frames → webp → SEO → render → check.
    """
    ctx.ensure_object(dict)
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(message)s" if verbose else "%(message)s"
    )
    ctx.obj["logger"] = logging.getLogger("cli")


@cli.command()
@click.option("--url", required=True, help="YouTube video URL")
@click.option("--cookies", help="Path to Netscape cookies file")
@click.option("--proxy", help="HTTP proxy (e.g. http://127.0.0.1:8080)")
@click.option("--output-dir", default="output", help="Output directory")
@click.option("--template", default="diyhub", help="HTML template name")
@click.option("--site-name", default="MakeDIYHub", help="Site name for SEO")
@click.option("--site-url", default="https://makediyhub.com", help="Site URL")
@click.option("--keyword", default="", help="Focus keyword")
@click.option("--category", default="DIY", help="Article category")
@click.option("--config", "config_path", default="configs/default.yaml", help="Pipeline config YAML path")
@click.option("--json", "json_output", is_flag=True, help="Output JSON result")
@click.pass_context
def run(ctx, url: str, cookies: Optional[str], proxy: Optional[str],
        output_dir: str, template: str, site_name: str, site_url: str,
        keyword: str, category: str, config_path: str, json_output: bool):
    """Run full pipeline on a single YouTube URL."""
    logger = ctx.obj["logger"]
    video_id = _extract_video_id(url)
    if not video_id:
        click.echo("Error: Could not extract video ID from URL", err=True)
        sys.exit(1)

    config = _build_config(config_path, {"output_dir": output_dir, "cookies": cookies or "",
                                          "proxy": proxy or "", "template": template,
                                          "site_name": site_name, "site_url": site_url})

    item = make_item("youtube", video_id, source_url=url, keyword=keyword, category=category)
    pipeline = Pipeline(config)
    result = pipeline.run(item)

    if result.status == "failed":
        click.echo(f"Pipeline failed: {result.error}", err=True)
        sys.exit(1)

    _print_result(result, json_output)


@cli.command()
@click.option("--csv", required=True, help="CSV file with keywords (columns: pillar,keyword,source,priority)")
@click.option("--category", default="DIY", help="Category label")
@click.option("--cookies", help="Path to cookies.txt")
@click.option("--output-dir", default="output", help="Output directory")
@click.option("--config", "config_path", default="configs/default.yaml", help="Pipeline config YAML")
@click.option("--limit", type=int, default=0, help="Max items to process")
@click.pass_context
def batch(ctx, csv: str, category: str, cookies: Optional[str],
          output_dir: str, config_path: str, limit: int):
    """Batch process keywords from CSV through YouTube pipeline.

    CSV format: pillar,keyword,source,priority

    Searches YouTube for each keyword, runs the best match through the full pipeline.
    """
    import csv as _csv
    import subprocess as _sp

    csv_path = Path(csv)
    if not csv_path.exists():
        click.echo(f"CSV not found: {csv_path}", err=True)
        sys.exit(1)

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(_csv.DictReader(f))

    if limit and limit > 0:
        rows = rows[:limit]

    success = 0
    failed = 0
    for i, row in enumerate(rows, 1):
        kw = row.get("keyword", "").strip()
        if not kw:
            continue

        click.echo(f"\n{'='*60}")
        click.echo(f"[{i}/{len(rows)}] {kw}")

        # Search YouTube
        vid = _search_youtube(kw, cookies)
        if not vid:
            click.echo(f"  No video found for '{kw}'")
            failed += 1
            continue

        click.echo(f"  Video: https://www.youtube.com/watch?v={vid}")

        config = _build_config(config_path, {"output_dir": output_dir, "cookies": cookies or "",
                                              "template": "diyhub", "site_name": "MakeDIYHub",
                                              "site_url": "https://makediyhub.com"})

        item = make_item("youtube", vid, source_url=f"https://www.youtube.com/watch?v={vid}",
                        keyword=kw, category=category)
        result = Pipeline(config).run(item)

        if result.status == "failed":
            failed += 1
            click.echo(f"  FAILED: {result.error}")
        else:
            success += 1
            click.echo(f"  OK — {result.artifacts.html_path}")

    click.echo(f"\n{'='*60}")
    click.echo(f"DONE: {success} success, {failed} failed, {len(rows)} total")


@cli.command()
@click.option("--output-dir", default="output", help="Pipeline output directory")
@click.option("--format", "fmt", type=click.Choice(["ts", "json"]), default="ts",
              help="Output format: ts (TypeScript) or json")
@click.pass_context
def export(ctx, output_dir: str, fmt: str):
    """Export pipeline state as blogs.ts entries or JSON.

    Reads pipeline state files from output/ and generates ready-to-use
    TypeScript entries for blogs.ts registration.
    """
    state_dir = Path(output_dir) / "state"
    if not state_dir.exists():
        state_dir = Path("output") / "state"
    if not state_dir.exists():
        click.echo("No pipeline state found. Run some pipelines first.", err=True)
        sys.exit(1)

    entries = []
    for sf in sorted(state_dir.glob("youtube_*.json")):
        try:
            state = json.loads(sf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if state.get("status") == "failed":
            continue
        vid = sf.stem.replace("youtube_", "")
        seo = state.get("seo", {})
        entries.append({
            "slug": _slugify(state.get("title", "untitled")),
            "pageTitle": f"{state.get('title', 'Untitled')} | MakeDIYHub",
            "h1Title": state.get("title", "Untitled"),
            "category": state.get("category", "DIY"),
            "date": state.get("completed_at", "")[:10] or "Unknown",
            "readTime": "5 min read",
            "youtubeId": vid,
            "excerpt": (seo.get("meta_description", "") or "")[:200],
            "htmlFile": state.get("artifacts", {}).get("html_path", "").split("/")[-1] or f"{vid}.html",
        })

    if fmt == "json":
        click.echo(json.dumps(entries, indent=2, ensure_ascii=False))
    else:
        for e in entries:
            click.echo(f"""  {{
    slug: '{e['slug']}',
    pageTitle: "{e['pageTitle']}",
    h1Title: "{e['h1Title']}",
    category: '{e['category']}',
    date: '{e['date']}',
    readTime: '{e['readTime']}',
    youtubeId: '{e['youtubeId']}',
    excerpt: "{e['excerpt']}",
    htmlFile: '{e['htmlFile']}',
  }},""")
        click.echo(f"\n// {len(entries)} entries", err=True)

@cli.command()
@click.option("--target", required=True, help="Path to diyhub-online project root")
@click.option("--output-dir", default="output", help="Pipeline output directory")
@click.option("--category", "cat_slug", default="tech", help="Category slug: tech/lifestyle")
@click.option("--dry-run", is_flag=True, help="Show what would be copied, don't copy")
@click.pass_context
def sync(ctx, target, output_dir, cat_slug, dry_run):
    """Sync pipeline output to diyhub-online website."""
    import shutil as _shutil

    state_dir = Path(output_dir) / "state"
    if not state_dir.exists():
        click.echo("No pipeline state found. Run some pipelines first.", err=True)
        sys.exit(1)

    target_p = Path(target)
    html_dir = target_p / "content" / "blogs"
    img_base = target_p / "public" / cat_slug

    copied = 0
    for sf in sorted(state_dir.glob("youtube_*.json")):
        try:
            state = json.loads(sf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if state.get("status") != "done":
            continue

        vid = state["source_id"]
        html_src = state.get("artifacts", {}).get("html_path", "")
        img_dir_src = state.get("artifacts", {}).get("images_dir", f"output/images/{vid}")

        # Copy HTML
        if html_src and Path(html_src).exists():
            dst = html_dir / Path(html_src).name
            if not dry_run:
                html_dir.mkdir(parents=True, exist_ok=True)
                _shutil.copy2(html_src, dst)
            click.echo(f"  HTML: {Path(html_src).name} -> content/blogs/")

        # Copy images
        img_dir = Path(img_dir_src)
        if img_dir.exists():
            dst_dir = img_base / vid
            if not dry_run:
                if dst_dir.exists():
                    _shutil.rmtree(dst_dir)
                _shutil.copytree(img_dir, dst_dir)
            count = len(list(img_dir.glob("*.webp"))) + len(list(img_dir.glob("*.jpg")))
            click.echo(f"  IMG:  {count} files -> public/{cat_slug}/{vid}/")

        copied += 1

    if dry_run:
        click.echo(f"\n[DRY RUN] Would sync {copied} articles to {target}")
    else:
        click.echo(f"\nSynced {copied} articles to {target}")
        click.echo("Run 'ytarticle export' to get blogs.ts entries for registration.")


@cli.command()
def templates():
    """List available templates."""
    from ytarticle.templates.base import list_templates
    for t in list_templates():
        click.echo(t)


def _build_config(config_path: str, overrides: dict) -> dict:
    import yaml
    p = Path(config_path)
    if p.exists():
        config = yaml.safe_load(p.read_text(encoding="utf-8"))
    else:
        config = _default_config(overrides)

    cookies = overrides.get("cookies", "")
    proxy = overrides.get("proxy", "")
    out = overrides["output_dir"]

    for step in config.get("steps", []):
        scfg = step.setdefault("config", {})
        sid = step.get("id", "")
        if sid in ("extract", "frames"):
            if cookies:
                scfg["cookies_path"] = cookies
            if proxy:
                scfg["proxy_http"] = proxy
        if sid == "seo":
            scfg.setdefault("site_name", overrides.get("site_name", "MakeDIYHub"))
        if sid == "render":
            scfg.setdefault("output_dir", f"{out}/html")
            scfg.setdefault("template", f"{overrides.get('template', 'diyhub')}/article.html")
            scfg.setdefault("site_url", overrides.get("site_url", "https://makediyhub.com"))
            scfg.setdefault("site_name", overrides.get("site_name", "MakeDIYHub"))
    return config


def _default_config(overrides: dict) -> dict:
    out = overrides["output_dir"]
    return {"steps": [
        {"component": "youtube_extract", "id": "extract", "config": {"output_dir": f"{out}/raw"}},
        {"component": "ai_rewrite", "id": "rewrite", "config": {"prompt_file": "prompts/rewrite_article.md"}},
        {"component": "youtube_frames", "id": "frames", "config": {"output_dir": f"{out}/images"}},
        {"component": "convert_webp", "id": "webp", "config": {"quality": 85}},
        {"component": "seo_metadata", "id": "seo", "config": {"prompt_file": "prompts/seo_metadata.md", "site_name": overrides["site_name"]}},
        {"component": "html_render", "id": "render", "config": {"output_dir": f"{out}/html", "template": f"{overrides.get('template', 'diyhub')}/article.html", "site_url": overrides["site_url"], "site_name": overrides["site_name"]}},
        {"component": "content_check", "id": "check", "config": {}},
    ]}


def _extract_video_id(url: str) -> Optional[str]:
    import re
    patterns = [
        r"(?:youtube\.com/watch\?.*v=)([a-zA-Z0-9_-]{11})",
        r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def _search_youtube(keyword: str, cookies: Optional[str]) -> Optional[str]:
    """Search YouTube for best matching video."""
    import subprocess as _sp
    import os as _os

    cmd = [sys.executable, "-m", "yt_dlp", "--dump-json", "--flat-playlist",
           f"ytsearch3:{keyword} diy tutorial"]
    if cookies:
        cmd += ["--cookies", cookies]

    try:
        result = _sp.run(cmd, capture_output=True, text=True, timeout=30)
    except (_sp.TimeoutExpired, OSError):
        return None

    if result.returncode != 0:
        return None

    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            info = json.loads(line)
            vid = info.get("id", "")
            dur = info.get("duration", 0) or 0
            if vid and 180 <= dur <= 1800:
                return vid
        except json.JSONDecodeError:
            continue
    return None


def _slugify(text: str) -> str:
    import re
    text = text.lower().replace("&", "and")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:80]


def _print_result(result, json_output: bool):
    click.echo(f"Article: {result.artifacts.html_path}")
    click.echo(f"Title: {result.title}")
    click.echo(f"Words: {len(result.article_md.split())}")
    if json_output:
        click.echo(json.dumps({
            "status": result.status,
            "title": result.title,
            "html_path": result.artifacts.html_path,
            "word_count": len(result.article_md.split()),
            "difficulty": result.difficulty,
            "images": len(result.images),
        }, indent=2))


if __name__ == "__main__":
    cli()