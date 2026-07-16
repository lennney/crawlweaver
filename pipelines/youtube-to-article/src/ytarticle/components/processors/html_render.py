"""HTML render — markdown to HTML with full Schema.org structured data."""
from __future__ import annotations
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader
import markdown as md_lib

from ytarticle.core.base import BaseComponent
from ytarticle.core.schema import ContentItem
from ytarticle.templates.base import resolve_template

logger = logging.getLogger("ytarticle.html_render")


class HtmlRender(BaseComponent):
    name = "html_render"
    version = "2.0.0"
    required_fields = ["article_md", "seo"]
    output_fields = ["artifacts.html_path"]

    def __init__(self):
        super().__init__()
        self._env: Optional[Environment] = None

    def _get_env(self, template_dir: Path) -> Environment:
        if self._env is None:
            self._env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=False)
        return self._env

    def _build_step_image_map(self, images: list) -> dict[int, str]:
        step_imgs: dict[int, str] = {}
        for img in images:
            step = getattr(img, 'step', 0) or img.get('step', 0)
            path = getattr(img, 'path', '') or img.get('path', '')
            if step and path:
                rel = path.replace("\\", "/")
                # Normalize: strip any prefix up to and including "images/"
                for sep in ("/output/images/", "output/images/", "/images/"):
                    if sep in rel:
                        rel = rel.split(sep, 1)[1]
                        break
                rel = f"../images/{rel}"
                step_imgs[step] = rel
        return step_imgs

    def _inject_step_images(self, body_html: str, images: list) -> str:
        step_imgs = self._build_step_image_map(images)
        if not step_imgs:
            return body_html

        def replacer(m: re.Match) -> str:
            step_num = int(m.group(1))
            if step_num in step_imgs:
                img = f'<img src="{step_imgs[step_num]}" alt="Step {step_num}" loading="lazy" style="width:100%;max-width:800px;border-radius:12px;margin:12px 0;border:1px solid #e2ddd5;">'
                return m.group(0) + "\n" + img
            return m.group(0)

        return re.sub(r'<strong>(?:\#*\s*)?(?:Step\s+)?(\d+)[.:].*?</strong>',
                      replacer, body_html, flags=re.IGNORECASE)

    def _parse_sections(self, md: str, images: list) -> tuple[list[dict], list[dict]]:
        """Parse markdown into sections with HTML body and FAQ items."""
        sections = []
        faq = []
        current = None
        current_lines = []
        in_faq = False

        def flush():
            nonlocal current, current_lines
            if current:
                body_html = md_lib.markdown("\n".join(current_lines).strip())
                if "step" in current.lower() or "step-by-step" in current.lower():
                    body_html = self._inject_step_images(body_html, images)
                sections.append({"id": self._slugify(current), "title": current, "body_html": body_html, "image": ""})
                current_lines = []
                current = None

        for line in md.split("\n"):
            if line.startswith("## FAQ") and not line.startswith("## FAQs"):
                flush()
                in_faq = True
                continue
            if in_faq:
                if line.startswith("## "):
                    in_faq = False
                else:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    if line.startswith("### "):
                        faq.append({"q": line[4:].strip(), "a": ""})
                        continue
                    q_match = re.match(r'\*\*Q:\s*(.+?)(?:\*\*)?(?:\s+A:\s*(.*))?$', stripped)
                    if q_match:
                        question = q_match.group(1).strip()
                        answer = q_match.group(2)
                        faq.append({"q": question, "a": ((answer or "").strip() + " ") if answer else ""})
                        continue
                    a_match = re.match(r'A:\s*(.*)', stripped)
                    if a_match and faq:
                        faq[-1]["a"] += a_match.group(1).strip() + " "
                        continue
                    if faq:
                        faq[-1]["a"] += stripped + " "
                    continue
            if line.startswith("## "):
                flush()
                current = line[3:].strip()
            elif line.startswith("### "):
                clean = line[4:].lstrip("#").strip()
                current_lines.append(f"**{clean}**")
            else:
                current_lines.append(line)
        flush()
        for item in faq:
            item["a"] = item["a"].strip()
        return sections, faq

    @staticmethod
    def _slugify(text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[\s_]+", "-", text)
        text = re.sub(r"-+", "-", text)
        return text.strip("-")[:80]

    @staticmethod
    def _parse_time_iso(time_str: str) -> Optional[str]:
        if not time_str:
            return None
        text = re.sub(r'\(.*?\)', '', time_str.lower()).strip()
        hours, minutes = 0, 0
        hr_range = re.search(r'(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(?:hour|hr)', text)
        if hr_range:
            hours = float(hr_range.group(2))
        else:
            hr_single = re.search(r'(\d+(?:\.\d+)?)\s*(?:hour|hr)', text)
            if hr_single:
                hours = float(hr_single.group(1))
        min_range = re.search(r'(\d+)\s*-\s*(\d+)\s*(?:min|minute)', text)
        if min_range:
            minutes = int(min_range.group(2))
        else:
            min_single = re.search(r'(\d+)\s*(?:min|minute)', text)
            if min_single:
                minutes = int(min_single.group(1))
        if hours:
            hours_int = int(hours)
            minutes += int(round((hours - hours_int) * 60))
            hours = hours_int
        if hours == 0 and minutes == 0:
            return None
        if hours and minutes:
            return f"PT{hours}H{minutes}M"
        elif hours:
            return f"PT{hours}H"
        return f"PT{minutes}M"

    @staticmethod
    def _parse_cost(cost_str: str) -> Optional[dict]:
        if not cost_str:
            return None
        text = cost_str.strip()
        currency = "USD"
        for sym, code in {"$": "USD", "£": "GBP", "€": "EUR"}.items():
            if sym in text:
                currency = code
                break
        clean = re.sub(r'\(.*?\)', '', text).replace(',', '')
        numbers = re.findall(r'(\d+(?:\.\d+)?)', clean)
        if not numbers:
            return None
        if len(numbers) >= 2:
            return {"@type": "MonetaryAmount", "currency": currency, "minValue": numbers[0], "maxValue": numbers[1]}
        return {"@type": "MonetaryAmount", "currency": currency, "value": numbers[0]}

    def _extract_howto_steps(self, article_md: str, images: list) -> list[dict]:
        step_imgs = self._build_step_image_map(images)
        sec_match = re.search(r'##\s+Step.*?(?=\n##[^#]|\Z)', article_md, re.DOTALL | re.IGNORECASE)
        if not sec_match:
            return []
        steps = []
        position = 0
        blocks = re.findall(
            r'###\s+Step\s+(\d+)[.:]\s*(.*?)(?=###\s+Step\s+\d+[.:]|\Z)',
            sec_match.group(), re.DOTALL | re.IGNORECASE)
        for step_num, content in blocks:
            position += 1
            lines = content.strip().split('\n')
            step_title = lines[0].strip() if lines else ""
            step_body = '\n'.join(lines[1:]).strip()
            step_body = re.sub(r'!\[.*?\]\(.*?\)', '', step_body)
            step_body = re.sub(r'\*\*(.+?)\*\*', r'\1', step_body)
            step_body = re.sub(r'\*(.+?)\*', r'\1', step_body)
            step_body = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', step_body)
            step_body = re.sub(r'\n{2,}', '\n', step_body).strip()[:500]
            s: dict = {"@type": "HowToStep", "position": position, "name": step_title or f"Step {step_num}", "text": step_body}
            if int(step_num) in step_imgs:
                s["image"] = step_imgs[int(step_num)]
            steps.append(s)
        return steps

    def run(self, item: ContentItem, config: dict[str, Any]) -> ContentItem:
        template_name = config.get("template", "diyhub/article.html")
        custom_dirs = config.get("template_dirs", [])
        site_url = config.get("site_url", "https://makediyhub.com")
        site_name = config.get("site_name", "MakeDIYHub")
        date_published = (item.started_at or datetime.now().isoformat())[:10]

        template_dir, resolved_name = resolve_template(template_name, custom_dirs=custom_dirs)
        env = self._get_env(template_dir)
        template = env.get_template(resolved_name)

        sections, faq = self._parse_sections(item.article_md, item.images)
        url_slug = item.seo.url_slug or f"/diy/{item.source_id}"

        # Word count
        word_count = len(item.article_md.split())
        reading_time = max(1, round(word_count / 200))

        # Schema.org: HowTo
        cover = item.artifacts.cover_img or ""
        howto_schema: dict = {
            "@context": "https://schema.org",
            "@type": "HowTo",
            "name": item.seo.h1 or item.title,
            "description": item.seo.meta_description or "",
            "datePublished": date_published,
            "dateModified": date_published,
            "author": {"@type": "Organization", "name": site_name},
        }
        if cover:
            howto_schema["image"] = cover
        howto_steps = self._extract_howto_steps(item.article_md, item.images)
        if howto_steps:
            howto_schema["step"] = howto_steps
        if item.materials:
            howto_schema["supply"] = [{"@type": "HowToSupply", "name": m} for m in item.materials if m.strip()]
        total_time = self._parse_time_iso(item.estimated_time)
        if total_time:
            howto_schema["totalTime"] = total_time
        cost = self._parse_cost(item.estimated_cost)
        if cost:
            howto_schema["estimatedCost"] = cost

        # Schema.org: Article
        article_url = f"{site_url}{url_slug}"
        article_schema: dict = {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": item.seo.h1 or item.title,
            "description": item.seo.meta_description or "",
            "datePublished": date_published,
            "dateModified": date_published,
            "author": {"@type": "Organization", "name": site_name},
            "publisher": {"@type": "Organization", "name": site_name},
            "url": article_url,
            "mainEntityOfPage": {"@type": "WebPage", "@id": article_url},
            "inLanguage": "en",
            "wordCount": word_count,
        }
        if cover:
            article_schema["image"] = cover

        # Schema.org: BreadcrumbList
        category = item.category or "DIY"
        breadcrumb_schema = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": site_url},
                {"@type": "ListItem", "position": 2, "name": category, "item": f"{site_url}/{self._slugify(category)}"},
                {"@type": "ListItem", "position": 3, "name": item.seo.h1 or item.title, "item": article_url},
            ],
        }

        # Schema.org: FAQPage
        faq_schema_json = None
        if faq:
            faq_entities = [{"@type": "Question", "name": f["q"],
                            "acceptedAnswer": {"@type": "Answer", "text": f["a"]}} for f in faq if f.get("q") and f.get("a")]
            if faq_entities:
                faq_schema_json = json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": faq_entities}, ensure_ascii=False, indent=2)

        # TOC
        toc_items = [{"cls": "toc-h2", "id": "intro", "label": "Overview"}]
        for s in sections:
            toc_items.append({"cls": "toc-h2", "id": s["id"], "label": s["title"]})
        if faq:
            toc_items.append({"cls": "toc-h2", "id": "faq", "label": "FAQ"})

        # Tags and keywords
        meta_keywords = ", ".join(filter(None, [category, item.keyword])) or category
        tags = item.tags if item.tags else ([item.keyword] if item.keyword else [])

        # Source label
        source_label = ""
        if item.source.value == "youtube" and item.source_url:
            source_label = "YouTube"
        elif item.source.value == "reddit":
            source_label = "Reddit"

        html = template.render(
            title_tag=item.seo.title_tag or f"{item.title} | {site_name}",
            meta_description=item.seo.meta_description or "",
            meta_keywords=meta_keywords,
            category=category,
            category_slug=self._slugify(category),
            h1=item.seo.h1 or item.title,
            cover_image=cover,
            difficulty=item.difficulty.title() if item.difficulty else "Medium",
            estimated_time=item.estimated_time or "Varies",
            estimated_cost=item.estimated_cost or "Varies",
            material_count=len(item.materials),
            reading_time=reading_time,
            tags=tags,
            source=item.source.value,
            source_label=source_label,
            source_url=item.source_url or "",
            toc_items=toc_items,
            sections=sections,
            faq=faq,
            howto_schema_json=json.dumps(howto_schema, ensure_ascii=False, indent=2),
            article_schema_json=json.dumps(article_schema, ensure_ascii=False, indent=2),
            breadcrumb_schema_json=json.dumps(breadcrumb_schema, ensure_ascii=False, indent=2),
            faq_schema_json=faq_schema_json,
            SITE_URL=site_url,
            url_slug=url_slug,
            date_published=date_published,
        )

        output_dir = Path(config.get("output_dir", "output/html"))
        output_dir.mkdir(parents=True, exist_ok=True)
        slug = self._slugify(item.seo.h1 or item.title)
        output_path = output_dir / f"{item.source_id}-{slug}.html"
        output_path.write_text(html, encoding="utf-8")
        item.artifacts.html_path = str(output_path)
        logger.info(f"[html_render] Wrote {output_path}")
        return item


def create():
    return HtmlRender()