"""Smoke tests for the web dashboard (Task 8)."""
import pytest
from pathlib import Path


def test_fastapi_app_loads():
    """FastAPI app should import and have correct routes."""
    from web.app import app
    routes = [r.path for r in app.routes]
    assert "/" in routes
    assert "/api/health" in routes
    assert "/api/stats" in routes
    assert "/api/jobs" in routes
    assert "/api/knowledge" in routes
    assert "/api/articles" in routes


@pytest.mark.asyncio
async def test_health_endpoint():
    """Health endpoint should return OK."""
    from httpx import AsyncClient, ASGITransport
    from web.app import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "2.0"


@pytest.mark.asyncio
async def test_jobs_endpoint(tmp_path, monkeypatch):
    """Jobs endpoint should return HTML table."""
    from httpx import AsyncClient, ASGITransport
    from web.app import app
    import web.api as api_module

    # Patch DATA_DIR to use tmp_path
    monkeypatch.setattr(api_module, "DATA_DIR", tmp_path)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/jobs")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "No jobs yet" in resp.text or "<table" in resp.text


@pytest.mark.asyncio
async def test_knowledge_endpoint_empty(tmp_path, monkeypatch):
    """Knowledge endpoint should handle missing knowledge.json."""
    from httpx import AsyncClient, ASGITransport
    from web.app import app
    import web.api as api_module

    monkeypatch.setattr(api_module, "DATA_DIR", tmp_path)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/knowledge")
        assert resp.status_code == 200
        data = resp.json()
        assert "crawled_urls" in data


@pytest.mark.asyncio
async def test_articles_endpoint_empty(tmp_path, monkeypatch):
    """Articles endpoint should handle missing output dir."""
    from httpx import AsyncClient, ASGITransport
    from web.app import app
    import web.api as api_module

    monkeypatch.setattr(api_module, "DATA_DIR", tmp_path)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/articles")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "No articles" in resp.text


@pytest.mark.asyncio
async def test_dashboard_renders():
    """Dashboard page should return HTML."""
    from httpx import AsyncClient, ASGITransport
    from web.app import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "AI Crawler" in resp.text
        assert "htmx" in resp.text
