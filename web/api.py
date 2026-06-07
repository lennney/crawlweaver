"""API routes for the dashboard."""
import json
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(prefix="/api")
DATA_DIR = Path(__file__).parent.parent


@router.get("/jobs")
async def list_jobs():
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
    return {"jobs": jobs}


@router.post("/jobs")
async def create_job(request: Request, bg: BackgroundTasks):
    body = await request.json()
    bg.add_task(_run_crawl, body)
    return {"status": "submitted", "url": body.get("url")}


@router.get("/knowledge")
async def get_knowledge(request: Request):
    k_path = DATA_DIR / "knowledge.json"
    panel = request.query_params.get("panel")

    if panel == "patterns":
        # Return HTML fragment for patterns table
        if k_path.exists():
            data = json.loads(k_path.read_text())
        else:
            data = {"site_patterns": {}}

        patterns = data.get("site_patterns", {})
        if not patterns:
            return JSONResponse({"html": "<p class='text-gray-500'>No site patterns recorded yet.</p>"})

        rows = ""
        for domain, sp in patterns.items():
            avg_q = sp.get("avg_quality", 0)
            count = sp.get("sample_count", 0)
            extractor = sp.get("extractor", "unknown")
            prompt = sp.get("best_prompt", "—")
            rows += f"""<tr class="border-b border-gray-800">
                <td class="py-2 pr-4 text-gray-300">{domain}</td>
                <td class="py-2 pr-4 text-gray-400">{extractor}</td>
                <td class="py-2 pr-4 text-gray-400">{count}</td>
                <td class="py-2 pr-4 text-green-400">{avg_q:.1f}</td>
                <td class="py-2 text-gray-500 text-sm">{prompt}</td>
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
        return JSONResponse({"html": html})

    # Default: return full knowledge JSON
    if k_path.exists():
        data = json.loads(k_path.read_text())
        return data
    return {"crawled_urls": [], "site_patterns": {}, "prompt_stats": {}}


@router.get("/articles")
async def list_articles():
    output_dir = DATA_DIR / "output"
    articles = []
    if output_dir.exists():
        for f in sorted(output_dir.glob("*.html"), reverse=True):
            articles.append({"name": f.name})
    if not articles:
        return JSONResponse({"html": "<p class='text-gray-500'>No articles generated yet.</p>"})

    items = ""
    for a in articles:
        items += f"""<a href="/api/articles/{a['name']}" target="_blank"
            class="block bg-gray-800 hover:bg-gray-700 rounded px-4 py-3 mb-2 transition-colors">
            <span class="text-blue-400">📄</span>
            <span class="text-gray-200">{a['name']}</span>
        </a>"""
    return JSONResponse({"html": items})


@router.get("/articles/{name}")
async def get_article(name: str):
    path = DATA_DIR / "output" / name
    if path.exists():
        return FileResponse(path, media_type="text/html")
    return JSONResponse({"error": "not found"}, status_code=404)


def _run_crawl(body: dict):
    """Background task: run crawl pipeline."""
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
