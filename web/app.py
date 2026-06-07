"""Web Dashboard — FastAPI app.

Factor #11: Trigger from anywhere. Dashboard is just another entry point
that calls the same reducer.
"""
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="AI Crawler v2", version="2.0")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

from web.api import router
app.include_router(router)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(name="dashboard.html", context={"request": request})


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "2.0"}
