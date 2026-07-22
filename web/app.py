"""Web Dashboard — FastAPI app.

Factor #11: Trigger from anywhere. Dashboard is just another entry point
that calls the same reducer.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from task_queue import TaskQueue

task_queue = TaskQueue(max_workers=2)


@asynccontextmanager
async def lifespan(app):
    """Initialize task queue handler on startup."""
    from web.api import make_crawl_handler

    task_queue.set_handler(make_crawl_handler())
    yield


app = FastAPI(title="CrawlWeaver", lifespan=lifespan)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

from web.api import router  # noqa: E402

app.include_router(router)

# Bidirectional bot integrations
try:
    from bot.feishu import router as feishu_router

    app.include_router(feishu_router)
except ImportError:
    pass  # Feishu SDK not installed


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "2.0"}
