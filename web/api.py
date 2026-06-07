"""API routes for the dashboard."""
import csv
import json
import logging
from html import escape
from io import StringIO
from pathlib import Path
from typing import Callable
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from task_queue import Job, JobStatus, TaskQueue

logger = logging.getLogger("crawler.web")

router = APIRouter(prefix="/api")
DATA_DIR = Path(__file__).parent.parent

# Will be set by app.py at import time
_task_queue: "TaskQueue | None" = None


def get_queue() -> "TaskQueue":
    global _task_queue
    if _task_queue is None:
        from web.app import task_queue as tq
        _task_queue = tq
    return _task_queue


@router.get("/stats")
async def stats():
    """HTMX: return HTML stats cards."""
    k_path = DATA_DIR / "knowledge.json"
    if k_path.exists():
        data = json.loads(k_path.read_text())
    else:
        data = {}

    urls_count = len(data.get("crawled_urls", []))
    patterns_count = len(data.get("site_patterns", {}))
    prompt_stats = data.get("prompt_stats", {})
    avg_score = 0.0
    if prompt_stats:
        scores = [s.get("avg_score", 0) for s in prompt_stats.values() if s.get("count", 0) > 0]
        avg_score = sum(scores) / len(scores) if scores else 0
    failures_count = len(data.get("failure_log", []))

    cards = [
        ("Crawled URLs", str(urls_count), "text-blue-400"),
        ("Site Patterns", str(patterns_count), "text-green-400"),
        ("Avg Score", f"{avg_score:.0f}", "text-yellow-400"),
        ("Failures", str(failures_count), "text-red-400"),
    ]
    html = ""
    for label, value, color in cards:
        html += f"""<div class="bg-gray-900 rounded-lg p-4">
            <div class="text-gray-400 text-sm">{label}</div>
            <div class="text-2xl font-bold {color}">{value}</div>
        </div>"""
    return HTMLResponse(html)


@router.get("/jobs")
async def list_jobs():
    """HTMX: return HTML jobs table from task queue."""
    tq = get_queue()
    jobs = tq.list_jobs(limit=50)
    stats = tq.stats()

    if not jobs:
        return HTMLResponse("<p class='text-gray-500'>No jobs yet. Submit one above!</p>")

    step_colors = {
        "pending": "text-gray-400",
        "running": "text-blue-400 animate-pulse",
        "completed": "text-green-400",
        "failed": "text-red-400",
    }
    html = f"""<div class="flex gap-4 mb-4 text-sm">
        <span class="text-gray-400">⏳ {stats.get('pending', 0)} pending</span>
        <span class="text-blue-400">🔄 {stats.get('running', 0)} running</span>
        <span class="text-green-400">✅ {stats.get('completed', 0)} done</span>
        <span class="text-red-400">❌ {stats.get('failed', 0)} failed</span>
    </div>"""
    html += """<table class="w-full text-sm">
        <thead><tr class="text-left text-gray-500 border-b border-gray-700">
            <th class="pb-2 pr-4">URL</th>
            <th class="pb-2 pr-4">Keyword</th>
            <th class="pb-2 pr-4">Status</th>
        </tr></thead><tbody>"""
    for j in jobs:
        color = step_colors.get(j.status.value, "text-gray-300")
        html += f"""<tr class="border-b border-gray-800">
            <td class="py-2 pr-4 text-gray-300 truncate max-w-xs">{escape(j.url[:60])}</td>
            <td class="py-2 pr-4 text-gray-400">{escape(j.keyword)}</td>
            <td class="py-2 {color}">{escape(j.status.value)}</td>
        </tr>"""
    html += "</tbody></table>"
    return HTMLResponse(html)


@router.post("/jobs")
async def create_job(request: Request):
    """Submit a new crawl job via task queue."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    if not body.get("url"):
        return JSONResponse({"error": "url is required"}, status_code=400)

    tq = get_queue()
    job_id = tq.submit(
        url=body["url"],
        keyword=body.get("keyword", ""),
        source=body.get("source", "youtube"),
        content_type=body.get("content_type", "Beginner Guide"),
    )
    return JSONResponse({"status": "submitted", "job_id": job_id})


@router.get("/knowledge")
async def get_knowledge(request: Request):
    """Knowledge data — supports ?panel=patterns for HTML table."""
    k_path = DATA_DIR / "knowledge.json"
    panel = request.query_params.get("panel")

    if panel == "patterns":
        if k_path.exists():
            data = json.loads(k_path.read_text())
        else:
            data = {"site_patterns": {}}

        patterns = data.get("site_patterns", {})
        if not patterns:
            return HTMLResponse("<p class='text-gray-500'>No site patterns recorded yet.</p>")

        rows = ""
        for domain, sp in patterns.items():
            avg_q = sp.get("avg_quality", 0)
            count = sp.get("sample_count", 0)
            extractor = sp.get("extractor", "unknown")
            prompt = sp.get("best_prompt", "—")
            rows += f"""<tr class="border-b border-gray-800">
                <td class="py-2 pr-4 text-gray-300">{escape(domain)}</td>
                <td class="py-2 pr-4 text-gray-400">{escape(extractor)}</td>
                <td class="py-2 pr-4 text-gray-400">{count}</td>
                <td class="py-2 pr-4 text-green-400">{avg_q:.1f}</td>
                <td class="py-2 text-gray-500 text-sm">{escape(prompt)}</td>
            </tr>"""

        html = f"""<table class="w-full text-sm">
            <thead>
                <tr class="text-left text-gray-500 border-b border-gray-700">
                    <th class="pb-2 pr-4">Domain</th>
                    <th class="pb-2 pr-4">Extractor</th>
                    <th class="pb-2 pr-4">Samples</th>
                    <th class="pb-2 pr-4">Avg Quality</th>
                    <th class="pb-2">Best Prompt</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>"""
        return HTMLResponse(html)

    # Default: return full knowledge JSON (API consumers)
    if k_path.exists():
        return JSONResponse(json.loads(k_path.read_text()))
    return JSONResponse({"crawled_urls": [], "site_patterns": {}, "prompt_stats": {}})


@router.get("/articles")
async def list_articles():
    """HTMX: return HTML article list."""
    output_dir = DATA_DIR / "output"
    articles = []
    if output_dir.exists():
        for f in sorted(output_dir.glob("*.html"), reverse=True):
            articles.append({"name": f.name})

    if not articles:
        return HTMLResponse("<p class='text-gray-500'>No articles generated yet.</p>")

    items = ""
    for a in articles:
        name = escape(a['name'])
        items += f"""<a href="/api/articles/{name}" target="_blank"
            class="block bg-gray-800 hover:bg-gray-700 rounded px-4 py-3 mb-2 transition-colors">
            <span class="text-blue-400">📄</span>
            <span class="text-gray-200">{name}</span>
        </a>"""
    return HTMLResponse(items)


@router.get("/articles/{name}")
async def get_article(name: str):
    """Serve a generated HTML article."""
    path = DATA_DIR / "output" / name
    if path.exists():
        from fastapi.responses import FileResponse
        return FileResponse(path, media_type="text/html")
    return JSONResponse({"error": "not found"}, status_code=404)


@router.post("/batch")
async def batch_import(request: Request):
    """Upload CSV for batch import into task queue."""
    form = await request.form()
    csv_file = form.get("file")
    if not csv_file:
        return JSONResponse({"error": "No file"}, status_code=400)

    content = await csv_file.read()
    text = content.decode("utf-8")
    reader = csv.DictReader(StringIO(text))

    tq = get_queue()
    count = 0
    for row in reader:
        url = row.get("url", "").strip()
        if not url:
            continue
        tq.submit(
            url=url,
            keyword=row.get("keyword", "").strip(),
            source=row.get("source", "youtube").strip() or "youtube",
            content_type=row.get("content_type", "Beginner Guide").strip() or "Beginner Guide",
        )
        count += 1

    return HTMLResponse(f'<span class="text-green-400">✅ {count} jobs queued</span>')


def make_crawl_handler() -> Callable[[Job], None]:
    """Create a crawl handler for the task queue."""
    def handler(job: Job):
        from state import make_state
        from knowledge import load_knowledge, save_knowledge
        from llm import LLM
        from reducer import crawl

        state = make_state(
            url=job.url, source=job.source,
            keyword=job.keyword, content_type=job.content_type,
        )
        knowledge = load_knowledge(DATA_DIR / "knowledge.json")
        llm = LLM()
        states_dir = DATA_DIR / "states"
        states_dir.mkdir(parents=True, exist_ok=True)
        state_path = states_dir / f"{job.id}.json"
        state = crawl(state, knowledge, llm, state_path=str(state_path))
        save_knowledge(knowledge, DATA_DIR / "knowledge.json")
        job.result = {"step": state.step.value, "score": state.verify.score if state.verify else None}
    return handler
