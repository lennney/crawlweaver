"""API routes for the dashboard."""
import json
import logging
from html import escape
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

logger = logging.getLogger("crawler.web")

router = APIRouter(prefix="/api")
DATA_DIR = Path(__file__).parent.parent


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
    """HTMX: return HTML jobs table."""
    states_dir = DATA_DIR / "states"
    jobs = []
    if states_dir.exists():
        for f in sorted(states_dir.glob("*.json"), reverse=True)[:50]:
            try:
                data = json.loads(f.read_text())
                verify = data.get("verify")
                jobs.append({
                    "id": f.stem,
                    "url": data.get("url", ""),
                    "keyword": data.get("keyword", ""),
                    "step": data.get("step", "unknown"),
                    "score": verify.get("score") if verify else None,
                })
            except Exception:
                continue

    if not jobs:
        return HTMLResponse("<p class='text-gray-500'>No jobs yet. Submit one above!</p>")

    step_colors = {
        "passed": "text-green-400",
        "failed": "text-red-400",
        "pending": "text-gray-400",
        "extracted": "text-blue-400",
        "rewritten": "text-blue-400",
    }
    html = """<table class="w-full text-sm">
        <thead><tr class="text-left text-gray-500 border-b border-gray-700">
            <th class="pb-2 pr-4">URL</th>
            <th class="pb-2 pr-4">Keyword</th>
            <th class="pb-2 pr-4">Status</th>
            <th class="pb-2">Score</th>
        </tr></thead><tbody>"""
    for j in jobs:
        step = j["step"]
        color = step_colors.get(step, "text-gray-300")
        score = str(j["score"]) if j["score"] is not None else "—"
        html += f"""<tr class="border-b border-gray-800">
            <td class="py-2 pr-4 text-gray-300 truncate max-w-xs">{escape(j['url'][:60])}</td>
            <td class="py-2 pr-4 text-gray-400">{escape(j['keyword'])}</td>
            <td class="py-2 pr-4 {color}">{escape(step)}</td>
            <td class="py-2 text-gray-300">{score}</td>
        </tr>"""
    html += "</tbody></table>"
    return HTMLResponse(html)


@router.post("/jobs")
async def create_job(request: Request, bg: BackgroundTasks):
    """Submit a new crawl job."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    if not body.get("url"):
        return JSONResponse({"error": "url is required"}, status_code=400)
    bg.add_task(_run_crawl, body)
    return JSONResponse({"status": "submitted", "url": body.get("url")})


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
        return FileResponse(path, media_type="text/html")
    return JSONResponse({"error": "not found"}, status_code=404)


def _run_crawl(body: dict):
    """Background task: run crawl pipeline."""
    try:
        from state import make_state
        from knowledge import load_knowledge, save_knowledge
        from llm import LLM
        from reducer import crawl

        state = make_state(
            url=body.get("url", ""),
            source=body.get("source", "youtube"),
            keyword=body.get("keyword", ""),
        )
        knowledge = load_knowledge(DATA_DIR / "knowledge.json")
        llm = LLM()
        states_dir = DATA_DIR / "states"
        states_dir.mkdir(parents=True, exist_ok=True)
        state_path = states_dir / f"{hash(state.url) & 0xFFFFFF:06x}.json"
        state = crawl(state, knowledge, llm, state_path=str(state_path))
        save_knowledge(knowledge, DATA_DIR / "knowledge.json")
        logger.info(f"Crawl completed: {state.url} → {state.step.value}")
    except Exception as e:
        logger.exception(f"Crawl failed for {body.get('url', '?')}: {e}")
