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
from knowledge import load_knowledge

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
    knowledge = load_knowledge(k_path)
    data = knowledge.model_dump()
    data["crawled_urls"] = list(data.get("crawled_urls", []))

    urls_count = len(data.get("crawled_urls", []))
    prompt_stats = data.get("prompt_stats", {})
    avg_score = 0.0
    if prompt_stats:
        scores = [s.get("avg_score", 0) for s in prompt_stats.values() if s.get("count", 0) > 0]
        avg_score = sum(scores) / len(scores) if scores else 0

    # Cost stats
    article_costs = data.get("article_costs", [])
    total_cost = sum(a.get("total_cost_usd", 0) for a in article_costs)

    # Coverage stats
    coverage = data.get("keyword_coverage", {})
    covered_count = sum(1 for v in coverage.values() if v.get("covered"))

    # Queue stats (try to get from task queue)
    queue_pending = 0
    try:
        tq = get_queue()
        q_stats = tq.stats()
        queue_pending = q_stats.get("pending", 0) + q_stats.get("running", 0)
    except Exception:
        logger.warning("Failed to get queue stats", exc_info=True)

    cards = [
        ("URLs", str(urls_count), "text-blue-400"),
        ("Queue", str(queue_pending), "text-purple-400"),
        ("Score", f"{avg_score:.0f}", "text-yellow-400"),
        ("Cost", f"${total_cost:.4f}", "text-red-400"),
        ("Coverage", f"{covered_count}/{len(coverage)}", "text-green-400"),
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


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Get job status by ID (for progress polling)."""
    import json, fcntl
    tq = get_queue()
    job = tq.get_job(job_id)
    if not job:
        # Check state file for completed jobs
        state_path = DATA_DIR / "states" / f"{job_id}.json"
        if state_path.exists():
            with open(state_path, "r") as f:
                fcntl.flock(f, fcntl.LOCK_SH)
                try:
                    data = json.loads(f.read())
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
            return JSONResponse({
                "status": "completed",
                "job_id": job_id,
                "result": {
                    "step": data.get("step", ""),
                    "score": data.get("verify", {}).get("score", 0),
                    "title": data.get("title", ""),
                    "word_count": data.get("word_count", 0),
                    "html_path": data.get("html_path", ""),
                },
            })
        return JSONResponse({"error": "not found"}, status_code=404)

    return JSONResponse({
        "status": job.status.value,
        "job_id": job.id,
        "error": job.error,
        "result": {
            "url": job.url,
            "keyword": job.keyword,
        },
    })


@router.get("/knowledge")
async def get_knowledge(request: Request):
    """Knowledge data — supports ?panel=patterns for HTML table."""
    k_path = DATA_DIR / "knowledge.json"
    panel = request.query_params.get("panel")

    if panel == "patterns":
        knowledge = load_knowledge(k_path)
        data = knowledge.model_dump()

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
    knowledge = load_knowledge(k_path)
    data = knowledge.model_dump()
    data["crawled_urls"] = list(data.get("crawled_urls", []))
    return JSONResponse(data)


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
    # Path traversal protection
    if "/" in name or "\\" in name or ".." in name:
        return JSONResponse({"error": "invalid name"}, status_code=400)
    output_dir = (DATA_DIR / "output").resolve()
    path = (output_dir / name).resolve()
    if not path.is_relative_to(output_dir):
        return JSONResponse({"error": "forbidden"}, status_code=403)
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


@router.get("/costs")
async def get_costs():
    """HTMX: return cost statistics HTML panel."""
    k_path = DATA_DIR / "knowledge.json"
    knowledge = load_knowledge(k_path)
    article_costs = knowledge.model_dump().get("article_costs", [])

    if not article_costs:
        return HTMLResponse("<p class='text-gray-500'>No cost data yet.</p>")

    total = sum(a.get("total_cost_usd", 0) for a in article_costs)
    avg = total / len(article_costs) if article_costs else 0

    html = f"""<div class="grid grid-cols-2 gap-4 mb-4">
        <div class="bg-gray-800 rounded p-3">
            <div class="text-gray-400 text-sm">Total Cost</div>
            <div class="text-2xl font-bold text-green-400">${total:.4f}</div>
        </div>
        <div class="bg-gray-800 rounded p-3">
            <div class="text-gray-400 text-sm">Avg/Article</div>
            <div class="text-2xl font-bold text-yellow-400">${avg:.4f}</div>
        </div>
    </div>"""

    html += '<table class="w-full text-sm"><thead><tr class="text-left text-gray-500 border-b border-gray-700">'
    html += '<th class="pb-2 pr-4">Keyword</th><th class="pb-2 pr-4">Tokens</th><th class="pb-2 pr-4">Cost</th><th class="pb-2">Steps</th></tr></thead><tbody>'

    for a in reversed(article_costs):
        keyword = escape(a.get("keyword", "") or a.get("url", "")[:40])
        total_tokens = sum(s.get("tokens", 0) for s in a.get("steps", []))
        cost = a.get("total_cost_usd", 0)
        steps = ", ".join(s.get("step", "") for s in a.get("steps", []))
        html += f'<tr class="border-b border-gray-800">'
        html += f'<td class="py-2 pr-4 text-gray-300">{keyword}</td>'
        html += f'<td class="py-2 pr-4 text-gray-400">{total_tokens:,}</td>'
        html += f'<td class="py-2 pr-4 text-green-400">${cost:.4f}</td>'
        html += f'<td class="py-2 text-gray-500 text-xs">{escape(steps)}</td>'
        html += '</tr>'

    html += '</tbody></table>'
    return HTMLResponse(html)


@router.get("/trends")
async def quality_trends():
    """HTMX: return quality trend SVG chart."""
    states_dir = DATA_DIR / "states"
    scores = []
    if states_dir.exists():
        for f in sorted(states_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                verify = data.get("verify")
                if verify and verify.get("score"):
                    scores.append({
                        "keyword": data.get("keyword", ""),
                        "score": verify["score"],
                        "step": data.get("step", ""),
                    })
            except Exception:
                logger.debug("Skipping corrupted state file: %s", f.name)
                continue

    if not scores:
        return HTMLResponse("<p class='text-gray-500'>No scored articles yet.</p>")

    # Generate SVG line chart
    max_score = 100
    width = 600
    height = 200
    step_x = width / max(len(scores) - 1, 1)

    points = []
    for i, s in enumerate(scores):
        x = int(i * step_x)
        y = int(height - (s["score"] / max_score) * (height - 20))
        points.append(f"{x},{y}")

    polyline = " ".join(points)
    avg = sum(s["score"] for s in scores) / len(scores)

    svg = f"""<svg viewBox="0 0 {width} {height + 30}" class="w-full h-auto">
        <line x1="0" y1="{height}" x2="{width}" y2="{height}" stroke="#374151" stroke-width="1"/>
        <line x1="0" y1="0" x2="0" y2="{height}" stroke="#374151" stroke-width="1"/>
        <polyline points="{polyline}" fill="none" stroke="#3b82f6" stroke-width="2"/>
        <line x1="0" y1="{int(height - (avg/100)*(height-20))}" x2="{width}" y2="{int(height - (avg/100)*(height-20))}" stroke="#f59e0b" stroke-width="1" stroke-dasharray="4"/>
        <text x="{width}" y="{height + 15}" text-anchor="end" fill="#9ca3af" font-size="10">avg: {avg:.0f}</text>
        <text x="0" y="{height + 15}" fill="#9ca3af" font-size="10">articles: {len(scores)}</text>
    </svg>"""

    return HTMLResponse(svg)


@router.post("/publish")
async def publish_site():
    """Generate static site from published articles."""
    from publisher import generate_site
    site_dir = DATA_DIR / "site"
    generate_site(DATA_DIR / "output", site_dir, title="AI Content Hub")
    count = len(list(site_dir.glob("*.html"))) - 1  # exclude index
    return HTMLResponse(f'<span class="text-green-400">✅ Site generated: {count} articles + index + RSS</span>')


@router.get("/coverage")
async def get_coverage():
    """HTMX: return keyword coverage HTML panel."""
    k_path = DATA_DIR / "knowledge.json"
    knowledge = load_knowledge(k_path)
    coverage = knowledge.model_dump().get("keyword_coverage", {})

    if not coverage:
        return HTMLResponse("<p class='text-gray-500'>No keywords tracked yet.</p>")

    covered = [(k, v) for k, v in coverage.items() if v.get("covered")]
    uncovered = [(k, v) for k, v in coverage.items() if not v.get("covered")]

    html = f'<div class="mb-4 text-sm text-gray-400">'
    html += f'✅ {len(covered)} covered | ⏳ {len(uncovered)} targeted</div>'

    if covered:
        html += '<h4 class="text-md font-medium text-green-400 mb-2">✅ Covered</h4>'
        html += '<table class="w-full text-sm mb-4"><thead><tr class="text-left text-gray-500 border-b border-gray-700">'
        html += '<th class="pb-2 pr-4">Keyword</th><th class="pb-2 pr-4">Score</th><th class="pb-2">URL</th></tr></thead><tbody>'
        for kw, info in sorted(covered, key=lambda x: x[1].get("score", 0), reverse=True):
            html += f'<tr class="border-b border-gray-800"><td class="py-2 pr-4 text-gray-300">{escape(kw)}</td>'
            html += f'<td class="py-2 pr-4 text-green-400">{info.get("score", 0)}</td>'
            html += f'<td class="py-2 text-gray-500 text-xs truncate max-w-xs">{escape(info.get("article_url", ""))}</td></tr>'
        html += '</tbody></table>'

    if uncovered:
        html += '<h4 class="text-md font-medium text-yellow-400 mb-2">⏳ To Cover</h4><div class="flex flex-wrap gap-2">'
        for kw, _ in uncovered:
            html += f'<span class="bg-gray-800 text-gray-300 px-3 py-1 rounded text-sm">{escape(kw)}</span>'
        html += '</div>'

    return HTMLResponse(html)


@router.get("/review")
async def review_queue():
    """HTMX: return articles pending review."""
    states_dir = DATA_DIR / "states"
    pending = []
    if states_dir.exists():
        for f in sorted(states_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text())
                if data.get("step") == "review":
                    pending.append({
                        "id": f.stem,
                        "url": data.get("url", ""),
                        "keyword": data.get("keyword", ""),
                        "score": data.get("verify", {}).get("score", 0) if data.get("verify") else 0,
                        "html_path": data.get("html_path", ""),
                    })
            except Exception:
                logger.debug("Skipping corrupted state file: %s", f.name)
                continue

    if not pending:
        return HTMLResponse("<p class='text-gray-500'>No articles pending review.</p>")

    html = ""
    for p in pending:
        keyword = escape(p["keyword"] or p["url"][:50])
        score = p["score"]
        score_color = "text-green-400" if score >= 80 else "text-yellow-400" if score >= 60 else "text-red-400"
        preview = ""
        if p["html_path"]:
            name = Path(p["html_path"]).name
            preview = f'<a href="/api/articles/{escape(name)}" target="_blank" class="text-blue-400 hover:underline text-sm">Preview</a>'

        html += f"""<div class="bg-gray-800 rounded-lg p-4 mb-3 flex items-center justify-between">
            <div>
                <div class="text-gray-200 font-medium">{keyword}</div>
                <div class="text-sm {score_color}">Score: {score}/100</div>
                {preview}
            </div>
            <div class="flex gap-2">
                <button hx-post="/api/review/{escape(p['id'])}/approve" hx-swap="outerHTML"
                    class="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded text-sm">
                    ✅ Approve
                </button>
                <button hx-post="/api/review/{escape(p['id'])}/reject" hx-swap="outerHTML"
                    class="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded text-sm">
                    ❌ Reject
                </button>
            </div>
        </div>"""

    return HTMLResponse(html)


@router.post("/review/{job_id}/approve")
async def approve_article(job_id: str):
    """Approve an article — change step from REVIEW to PASSED."""
    import fcntl
    state_path = DATA_DIR / "states" / f"{job_id}.json"
    if not state_path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    with open(state_path, "r+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            data = json.loads(f.read())
            data["step"] = "passed"
            f.seek(0)
            f.truncate()
            json.dump(data, f, indent=2, ensure_ascii=False)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return HTMLResponse('<span class="text-green-400">✅ Approved</span>')


@router.post("/review/{job_id}/reject")
async def reject_article(job_id: str):
    """Reject an article — change step from REVIEW to FAILED."""
    import fcntl
    state_path = DATA_DIR / "states" / f"{job_id}.json"
    if not state_path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    with open(state_path, "r+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            data = json.loads(f.read())
            data["step"] = "failed"
            data["error"] = "Rejected by human reviewer"
            f.seek(0)
            f.truncate()
            json.dump(data, f, indent=2, ensure_ascii=False)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return HTMLResponse('<span class="text-red-400">❌ Rejected</span>')


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
