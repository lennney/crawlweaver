"""Static site publisher — generate index + RSS from output/ articles."""
import re
from datetime import datetime
from html import escape
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring


def generate_site(output_dir: Path, site_dir: Path, title: str = "AI Content Hub"):
    """Generate a static site from HTML articles."""
    site_dir.mkdir(parents=True, exist_ok=True)

    articles = []
    for html_file in sorted(output_dir.glob("*.html")):
        # Extract title from HTML
        content = html_file.read_text(encoding="utf-8")
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", content, re.IGNORECASE | re.DOTALL)
        article_title = h1.group(1).strip() if h1 else html_file.stem.replace("-", " ").title()

        # Copy article
        dest = site_dir / html_file.name
        dest.write_text(content, encoding="utf-8")

        articles.append({"file": html_file.name, "title": article_title})

    # Generate index.html
    index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    <link rel="alternate" type="application/rss+xml" title="RSS" href="/feed.xml">
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-950 text-gray-100 min-h-screen">
    <div class="max-w-4xl mx-auto p-6">
        <h1 class="text-3xl font-bold mb-8">{title}</h1>
        <div class="space-y-4">
"""
    for a in articles:
        fname = escape(a["file"])
        atitle = escape(a["title"])
        index_html += f'            <a href="{fname}" class="block bg-gray-900 hover:bg-gray-800 rounded-lg p-4 transition-colors">\n'
        index_html += f'                <h2 class="text-xl font-semibold text-blue-400">{atitle}</h2>\n'
        index_html += f'            </a>\n'

    index_html += """        </div>
        <footer class="mt-12 text-gray-500 text-sm">
            <a href="/feed.xml" class="hover:text-gray-300">RSS Feed</a>
        </footer>
    </div>
</body>
</html>"""

    (site_dir / "index.html").write_text(index_html, encoding="utf-8")
    generate_rss(output_dir, site_dir, title)


def generate_rss(output_dir: Path, site_dir: Path, title: str = "AI Content Hub",
                 base_url: str | None = None):
    """Generate RSS 2.0 feed."""
    import os
    if base_url is None:
        base_url = os.environ.get("CRAWLER_BASE_URL", "https://example.com")
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = title
    SubElement(channel, "link").text = base_url
    SubElement(channel, "description").text = f"{title} — AI-generated content"
    SubElement(channel, "lastBuildDate").text = datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")

    for html_file in sorted(output_dir.glob("*.html"), reverse=True)[:20]:
        content = html_file.read_text(encoding="utf-8")
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", content, re.IGNORECASE | re.DOTALL)
        article_title = h1.group(1).strip() if h1 else html_file.stem

        item = SubElement(channel, "item")
        SubElement(item, "title").text = article_title
        SubElement(item, "link").text = f"{base_url}/{html_file.name}"
        SubElement(item, "guid").text = f"{base_url}/{html_file.name}"

    rss_xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(rss, encoding="unicode")
    (site_dir / "feed.xml").write_text(rss_xml, encoding="utf-8")
