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


@pytest.mark.asyncio
async def test_create_job_endpoint():
    """POST /api/jobs should submit to queue."""
    from httpx import AsyncClient, ASGITransport
    from web.app import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/jobs", json={"url": "https://example.com", "keyword": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "submitted"
        assert "job_id" in data

@pytest.mark.asyncio
async def test_batch_import_no_file():
    """POST /api/batch without file should return 400."""
    from httpx import AsyncClient, ASGITransport
    from web.app import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/batch")
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_coverage_endpoint_empty(tmp_path, monkeypatch):
    """Coverage endpoint should handle missing data."""
    from httpx import AsyncClient, ASGITransport
    from web.app import app
    import web.api as api_module

    monkeypatch.setattr(api_module, "DATA_DIR", tmp_path)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/coverage")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_review_queue_empty(tmp_path, monkeypatch):
    """Review queue should handle empty states dir."""
    from httpx import AsyncClient, ASGITransport
    from web.app import app
    import web.api as api_module

    monkeypatch.setattr(api_module, "DATA_DIR", tmp_path)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/review")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "No articles pending review" in resp.text


@pytest.mark.asyncio
async def test_review_queue_with_pending(tmp_path, monkeypatch):
    """Review queue should show articles in review state."""
    import json
    from httpx import AsyncClient, ASGITransport
    from web.app import app
    import web.api as api_module

    monkeypatch.setattr(api_module, "DATA_DIR", tmp_path)
    states_dir = tmp_path / "states"
    states_dir.mkdir()

    # Create a review state
    state_data = {
        "url": "https://example.com/article",
        "keyword": "test keyword",
        "step": "review",
        "verify": {"score": 85, "passed": True},
        "html_path": str(tmp_path / "output" / "test.html"),
    }
    (states_dir / "job-001.json").write_text(json.dumps(state_data))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/review")
        assert resp.status_code == 200
        assert "test keyword" in resp.text
        assert "85" in resp.text
        assert "Approve" in resp.text


@pytest.mark.asyncio
async def test_approve_article(tmp_path, monkeypatch):
    """Approve endpoint should change step to passed."""
    import json
    from httpx import AsyncClient, ASGITransport
    from web.app import app
    import web.api as api_module

    monkeypatch.setattr(api_module, "DATA_DIR", tmp_path)
    states_dir = tmp_path / "states"
    states_dir.mkdir()

    state_data = {"url": "https://example.com", "keyword": "test", "step": "review"}
    (states_dir / "job-001.json").write_text(json.dumps(state_data))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/review/job-001/approve")
        assert resp.status_code == 200
        assert "Approved" in resp.text

        # Verify state changed
        data = json.loads((states_dir / "job-001.json").read_text())
        assert data["step"] == "passed"


@pytest.mark.asyncio
async def test_reject_article(tmp_path, monkeypatch):
    """Reject endpoint should change step to failed."""
    import json
    from httpx import AsyncClient, ASGITransport
    from web.app import app
    import web.api as api_module

    monkeypatch.setattr(api_module, "DATA_DIR", tmp_path)
    states_dir = tmp_path / "states"
    states_dir.mkdir()

    state_data = {"url": "https://example.com", "keyword": "test", "step": "review"}
    (states_dir / "job-001.json").write_text(json.dumps(state_data))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/review/job-001/reject")
        assert resp.status_code == 200
        assert "Rejected" in resp.text

        # Verify state changed
        data = json.loads((states_dir / "job-001.json").read_text())
        assert data["step"] == "failed"
        assert data["error"] == "Rejected by human reviewer"


@pytest.mark.asyncio
async def test_approve_article_not_found(tmp_path, monkeypatch):
    """Approve should return 404 for missing state."""
    from httpx import AsyncClient, ASGITransport
    from web.app import app
    import web.api as api_module

    monkeypatch.setattr(api_module, "DATA_DIR", tmp_path)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/review/nonexistent/approve")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_costs_endpoint_empty(tmp_path, monkeypatch):
    """Costs endpoint should handle missing data."""
    from httpx import AsyncClient, ASGITransport
    from web.app import app
    import web.api as api_module

    monkeypatch.setattr(api_module, "DATA_DIR", tmp_path)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/costs")
        assert resp.status_code == 200
        assert "No cost data yet" in resp.text
