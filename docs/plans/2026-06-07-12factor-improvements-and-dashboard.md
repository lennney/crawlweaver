# AI Crawler v2 — 12-Factor 改进 + Web Dashboard

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 修复 12-Factor 审计发现的 4 个问题，然后构建一个 Web Dashboard 用于管理爬虫任务。

**Architecture:** Phase 1 改进核心模块（context/reducer/knowledge/tools），Phase 2 用 FastAPI + 原生 HTML 构建轻量 Dashboard，复用现有 reducer 入口。

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, Pydantic, HTMX (no React/Vue)

---

## Phase 1: 12-Factor Improvements

### Task 1: Factor #3 — 提取 context.py 中的 magic numbers

**Objective:** 把硬编码的 `[:3000]` `[:4000]` `[:2000]` 提成常量。

**Files:**
- Modify: `context.py`
- Create: `tests/test_context.py`

**Step 1: Write failing test**
```python
# tests/test_context.py
"""Tests for context module — constants and context building."""
from context import (
    MAX_SOURCE_CHARS, MAX_ARTICLE_CHARS, MAX_ARTICLE_PREVIEW_CHARS,
    build_rewrite_context, build_seo_context, build_verify_context,
)
from state import make_state
from knowledge import Knowledge


def test_constants_exist():
    """Factor #3: context constants should be defined, not magic numbers."""
    assert isinstance(MAX_SOURCE_CHARS, int)
    assert isinstance(MAX_ARTICLE_CHARS, int)
    assert isinstance(MAX_ARTICLE_PREVIEW_CHARS, int)
    assert MAX_SOURCE_CHARS > 0
    assert MAX_ARTICLE_CHARS > 0
    assert MAX_ARTICLE_PREVIEW_CHARS > 0


def test_rewrite_context_truncates():
    """Source content should be truncated to MAX_SOURCE_CHARS."""
    state = make_state("https://example.com", keyword="test")
    state.raw_text = "x" * 10000
    ctx = build_rewrite_context(state, Knowledge())
    assert "x" * (MAX_SOURCE_CHARS + 1) not in ctx


def test_seo_context_truncates():
    """SEO context should truncate article to MAX_ARTICLE_PREVIEW_CHARS."""
    state = make_state("https://example.com", keyword="test")
    state.article_md = "y" * 5000
    ctx = build_seo_context(state)
    assert "y" * (MAX_ARTICLE_PREVIEW_CHARS + 1) not in ctx


def test_verify_context_truncates():
    """Verify context should truncate article to MAX_ARTICLE_CHARS."""
    state = make_state("https://example.com", keyword="test")
    state.raw_text = "x" * 10000
    state.article_md = "y" * 10000
    ctx = build_verify_context(state)
    assert "y" * (MAX_ARTICLE_CHARS + 1) not in ctx
```

**Step 2: Run test to verify failure**
Run: `cd /home/hermes/ai-crawler-v2 && python -m pytest tests/test_context.py -v`
Expected: FAIL (constants don't exist yet)

**Step 3: Write implementation**
In `context.py`, add constants after imports and replace all magic numbers:
```python
# Add after imports:
MAX_SOURCE_CHARS = 3000
MAX_ARTICLE_CHARS = 4000
MAX_ARTICLE_PREVIEW_CHARS = 2000

# Replace in build_rewrite_context:
f"## Source Content\n{state.raw_text[:MAX_SOURCE_CHARS]}"

# Replace in build_seo_context:
f"## Article (first {MAX_ARTICLE_PREVIEW_CHARS} chars)\n{state.article_md[:MAX_ARTICLE_PREVIEW_CHARS]}"

# Replace in build_verify_context:
f"## Original Source (first {MAX_SOURCE_CHARS} chars)\n{state.raw_text[:MAX_SOURCE_CHARS]}"
f"## Generated Article (first {MAX_ARTICLE_CHARS} chars)\n{state.article_md[:MAX_ARTICLE_CHARS]}"
```

**Step 4: Run test to verify pass**
Run: `cd /home/hermes/ai-crawler-v2 && python -m pytest tests/test_context.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add context.py tests/test_context.py
git commit -m "refactor: extract context magic numbers to constants (Factor #3)"
```

**Acceptance Criteria:**
1. 三个常量定义在 context.py 顶部
2. build_rewrite_context / build_seo_context / build_verify_context 都使用常量
3. 所有 4 个测试通过

---

### Task 2: Factor #4 — 共享 JSON parser + LLM 输出验证

**Objective:** 提取 seo.py 和 verify.py 中重复的 JSON 解析逻辑为共享模块，给 rewrite.py 加输出验证。

**Files:**
- Create: `tools/parse.py`
- Modify: `tools/seo.py` — 删除本地 `_parse_json`，改用共享版
- Modify: `tools/verify.py` — 删除 JSON 提取部分，改用共享版，保留类型规范化
- Modify: `tools/rewrite.py` — 加 `parse_llm_output` 验证
- Create: `tests/test_parse.py`

**Step 1: Write failing test**
```python
# tests/test_parse.py
"""Tests for shared JSON parse utility."""
import pytest
from tools.parse import parse_json, parse_llm_output


class TestParseJson:
    def test_valid_json(self):
        assert parse_json('{"a": 1}') == {"a": 1}

    def test_json_in_code_block(self):
        text = '```json\n{"a": 1}\n```'
        assert parse_json(text) == {"a": 1}

    def test_json_with_surrounding_text(self):
        text = 'Here is the result: {"a": 1} done.'
        assert parse_json(text) == {"a": 1}

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            parse_json("no json here")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            parse_json("")


class TestParseLlmOutput:
    def test_normal_markdown(self):
        result = parse_llm_output("# Title\n\nSome content.", min_length=5)
        assert result == "# Title\n\nSome content."

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            parse_llm_output("")

    def test_too_short_raises(self):
        with pytest.raises(ValueError, match="too short"):
            parse_llm_output("hi", min_length=100)

    def test_strips_think_tags(self):
        result = parse_llm_output("<think>reasoning</think>\n\n# Article\nContent here.")
        assert "<think>" not in result
        assert "# Article" in result
```

**Step 2: Run test to verify failure**
Run: `cd /home/hermes/ai-crawler-v2 && python -m pytest tests/test_parse.py -v`
Expected: FAIL

**Step 3: Create tools/parse.py**
```python
# tools/parse.py
"""Shared parsing utilities for LLM output.

Factor #4: Tools are structured outputs.
Centralizes JSON extraction and output validation.
"""
import json
import re


def parse_json(text: str) -> dict:
    """Extract JSON from LLM response. Tries 3 strategies.
    
    1. Direct json.loads
    2. Extract from ```json...``` code block
    3. Find first { to last }
    
    Raises ValueError if no valid JSON found.
    """
    if not text or not text.strip():
        raise ValueError("Cannot parse JSON from empty string")

    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: code block
    m = re.search(r"```(?:json)?\s*\n?(.+?)\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: first { to last }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Cannot parse JSON from LLM response: {text[:200]}")


def parse_llm_output(text: str, min_length: int = 50) -> str:
    """Validate and clean LLM text output.
    
    - Strips <think> tags
    - Checks minimum length
    - Raises ValueError on empty/invalid output
    """
    if not text or not text.strip():
        raise ValueError("LLM returned empty output")

    # Strip <think>...</think> blocks (some models include reasoning)
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    if len(cleaned) < min_length:
        raise ValueError(f"LLM output too short ({len(cleaned)} < {min_length}): {cleaned[:100]}")

    return cleaned
```

**Step 4: Update seo.py**
- Remove the entire `_parse_json` function (lines 62-87)
- Add at top: `from tools.parse import parse_json`
- In `seo()`, change `metadata = _parse_json(result)` → `metadata = parse_json(result)`

**Step 5: Update verify.py**
- Remove the JSON extraction part from `_parse_verify_json` (the try/except chains, lines 82-94)
- Add at top: `from tools.parse import parse_json`
- Replace the JSON extraction with: `data = parse_json(text)`
- Keep the type normalization loop (lines 96-113) as-is

**Step 6: Update rewrite.py**
- Add at top: `from tools.parse import parse_llm_output`
- Change `result = llm.call(...)` → `result = parse_llm_output(llm.call(...))`

**Step 7: Run tests**
Run: `cd /home/hermes/ai-crawler-v2 && python -m pytest tests/test_parse.py tests/test_reducer.py -v`
Expected: PASS

**Step 8: Commit**
```bash
git add tools/parse.py tools/seo.py tools/verify.py tools/rewrite.py tests/test_parse.py
git commit -m "refactor: shared JSON parser + LLM output validation (Factor #4)"
```

**Acceptance Criteria:**
1. tools/parse.py 存在且包含 parse_json + parse_llm_output
2. seo.py 不再有本地 _parse_json
3. verify.py 使用共享 parse_json（保留类型规范化）
4. rewrite.py 使用 parse_llm_output 验证输出
5. 所有测试通过

---

### Task 3: Factor #6 — Reducer 自动保存 state (WAL 模式)

**Objective:** 每步完成后自动写 state.json，进程崩溃可恢复。

**Files:**
- Modify: `reducer.py` — crawl() 加 state_path 参数
- Modify: `cli.py` — 传 state_path
- Create: `tests/test_wal.py`

**Step 1: Write failing test**
```python
# tests/test_wal.py
"""Tests for WAL auto-save (Factor #6)."""
from unittest.mock import MagicMock, patch
from pathlib import Path
from state import make_state, Step
from knowledge import Knowledge


def test_crawl_accepts_state_path():
    """crawl() should accept state_path parameter."""
    from reducer import crawl
    import inspect
    sig = inspect.signature(crawl)
    assert "state_path" in sig.parameters


def test_checkpoint_saves_after_each_step(tmp_path):
    """State file should be written after each pipeline step."""
    state_path = tmp_path / "state.json"
    
    # Create a minimal state that will fail at extract (no real URL)
    state = make_state("https://invalid.test/nope", keyword="test")
    knowledge = Knowledge()
    llm = MagicMock()
    
    from reducer import crawl
    # This will fail at extract, but state_path should still be written
    result = crawl(state, knowledge, llm, state_path=str(state_path))
    
    # State should have been saved at least once
    assert state_path.exists(), "WAL: state should be saved even on failure"
    saved = make_state.__func__.__class__.load(str(state_path))
    assert saved.url == "https://invalid.test/nope"
```

**Step 2: Implement WAL in reducer.py**
Add `state_path` parameter to `crawl()`:
```python
def crawl(state: CrawlState, knowledge: Knowledge, llm: LLM, state_path: str = None) -> CrawlState:
    """..."""
    
    def _checkpoint():
        """Factor #6: auto-save state after each step."""
        if state_path:
            try:
                state.save(state_path)
            except Exception as e:
                logger.warning(f"WAL checkpoint failed: {e}")
    
    # After each step, call _checkpoint():
    state = extract(state)
    _checkpoint()
    if state.error: return state
    
    state = rewrite(state, llm, knowledge)
    _checkpoint()
    if state.error: return state
    
    # ... etc for seo, render, verify
```

**Step 3: Update cli.py**
```python
# In cmd_crawl, after state creation:
state_dir = Path(args.knowledge).parent / "states"
state_dir.mkdir(parents=True, exist_ok=True)
state_hash = f"{hash(state.url) & 0xFFFFFF:06x}"
auto_state_path = str(state_dir / f"{state_hash}.json")

# Pass to crawl:
state = crawl(state, knowledge, llm, state_path=auto_state_path)
```

**Step 4: Run tests**
Run: `cd /home/hermes/ai-crawler-v2 && python -m pytest tests/test_wal.py tests/test_reducer.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add reducer.py cli.py tests/test_wal.py
git commit -m "feat: auto-save state after each step — WAL mode (Factor #6)"
```

**Acceptance Criteria:**
1. crawl() 接受 state_path 参数
2. 每步完成后调用 _checkpoint()
3. CLI 自动传 state_path（states/ 目录）
4. 测试通过

---

### Task 4: Factor #7 + #13 — 失败通知 + site_patterns 写入

**Objective:**
- Factor #7: 失败时设置结构化 failure_report
- Factor #13: verify 通过后写入 site_pattern

**Files:**
- Modify: `state.py` — 加 failure_report 字段
- Modify: `knowledge.py` — 加 record_site_pattern + SitePattern.total_quality
- Modify: `reducer.py` — PASSED 写 site_pattern, FAILED 设 failure_report
- Modify: `cli.py` — 输出失败报告
- Create: `tests/test_knowledge.py`

**Step 1: Write failing test**
```python
# tests/test_knowledge.py
"""Tests for knowledge module — site patterns and failure reports."""
from knowledge import Knowledge, SitePattern


def test_record_site_pattern():
    knowledge = Knowledge()
    knowledge.record_site_pattern(
        domain="youtube.com", extractor="youtube",
        prompt="prompts/rewrite.md", quality=85,
    )
    assert "youtube.com" in knowledge.site_patterns
    sp = knowledge.site_patterns["youtube.com"]
    assert sp.extractor == "youtube"
    assert sp.sample_count == 1
    assert sp.avg_quality == 85.0


def test_record_site_pattern_updates_avg():
    knowledge = Knowledge()
    knowledge.record_site_pattern("youtube.com", "youtube", "prompts/rewrite.md", 80)
    knowledge.record_site_pattern("youtube.com", "youtube", "prompts/rewrite.md", 90)
    sp = knowledge.site_patterns["youtube.com"]
    assert sp.sample_count == 2
    assert sp.avg_quality == 85.0


def test_site_pattern_has_total_quality():
    """SitePattern should have total_quality accumulator."""
    sp = SitePattern(extractor="web", best_prompt="p.md", avg_quality=80.0, sample_count=1, total_quality=80.0)
    assert sp.total_quality == 80.0


def test_failure_report_field():
    """CrawlState should have failure_report field."""
    from state import make_state
    state = make_state("https://example.com", keyword="test")
    assert state.failure_report is None
    state.failure_report = {"url": "https://example.com", "error": "test"}
    assert state.failure_report["error"] == "test"
```

**Step 2: Update state.py**
Add to CrawlState (after verify field):
```python
failure_report: Optional[dict] = None
```

**Step 3: Update knowledge.py**
Add `total_quality: float = 0.0` to SitePattern.
Add `record_site_pattern` method to Knowledge.

**Step 4: Update reducer.py**
In PASSED branch (after `knowledge.record_crawl`):
```python
from urllib.parse import urlparse
domain = urlparse(state.url).netloc
knowledge.record_site_pattern(
    domain=domain,
    extractor=state.source.value,
    prompt="prompts/rewrite.md",
    quality=state.verify.score,
)
```

In FAILED branch:
```python
state.failure_report = {
    "url": state.url,
    "keyword": state.keyword,
    "error": state.error,
    "step": state.step.value,
    "attempts": state.attempts,
}
```

**Step 5: Update cli.py**
After crawl, add failure report output:
```python
if state.failure_report:
    print(f"\n❌ FAILED — needs human review:")
    print(f"  URL: {state.failure_report['url']}")
    print(f"  Error: {state.failure_report['error']}")
    print(f"  Attempts: {state.failure_report['attempts']}")
```

**Step 6: Run tests**
Run: `cd /home/hermes/ai-crawler-v2 && python -m pytest tests/ -v`
Expected: PASS

**Step 7: Commit**
```bash
git add state.py knowledge.py reducer.py cli.py tests/test_knowledge.py
git commit -m "feat: failure reports (Factor #7) + site_patterns recording (Factor #13)"
```

**Acceptance Criteria:**
1. SitePattern 有 total_quality 字段
2. Knowledge.record_site_pattern() 正确计算移动平均
3. CrawlState 有 failure_report 字段
4. reducer PASSED 后写入 site_pattern
5. reducer FAILED 后设置 failure_report
6. cli 输出失败报告
7. 所有测试通过

---

## Phase 2: Web Dashboard

### Task 5: FastAPI 应用骨架

**Objective:** 创建 FastAPI 后端，提供 API + 页面路由。

**Files:**
- Create: `web/__init__.py`
- Create: `web/app.py`
- Create: `web/api.py`
- Create: `web/templates/base.html`
- Create: `web/templates/dashboard.html`
- Modify: `requirements.txt` — add: `fastapi>=0.115.0` and `uvicorn[standard]>=0.34.0`
- Modify: `cli.py` — add `dashboard` subcommand

**Step 1: Install dependencies**
```bash
cd /home/hermes/ai-crawler-v2 && uv pip install fastapi uvicorn[standard]
```

**Step 2: Create web/__init__.py** (empty)

**Step 3: Create web/app.py**
```python
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

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "2.0"}
```

**Step 4: Create web/templates/base.html**
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{% block title %}AI Crawler v2{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@2.0.4"></script>
</head>
<body class="bg-gray-950 text-gray-100 min-h-screen">
    {% block content %}{% endblock %}
</body>
</html>
```

**Step 5: Create web/templates/dashboard.html**
```html
{% extends "base.html" %}
{% block content %}
<div class="max-w-7xl mx-auto p-6">
    <h1 class="text-2xl font-bold mb-6">🕷️ AI Crawler v2</h1>
    <p class="text-gray-400">Dashboard loading...</p>
</div>
{% endblock %}
```

**Step 6: Add CLI command to cli.py**
```python
# Add to subparsers:
p_dash = sub.add_parser("dashboard", help="Launch web dashboard")
p_dash.add_argument("--port", type=int, default=8080)
p_dash.add_argument("--host", default="0.0.0.0")

# Add handler:
elif args.command == "dashboard":
    import uvicorn
    uvicorn.run("web.app:app", host=args.host, port=args.port, reload=True)
```

**Step 7: Commit**
```bash
git add web/ requirements.txt cli.py
git commit -m "feat: FastAPI dashboard skeleton (Factor #11)"
```

**Acceptance Criteria:**
1. `python cli.py dashboard` 启动 web server
2. http://localhost:8080/ 返回 HTML 页面
3. /api/health 返回 {"status": "ok"}
4. 页面使用 Tailwind + HTMX

---

### Task 6: Dashboard API — 爬虫任务管理

**Objective:** 提交新任务、查看任务列表、查看知识库统计。

**Files:**
- Modify: `web/api.py`
- Modify: `web/app.py` (include router)
- Modify: `web/templates/dashboard.html`

**API Endpoints:**
```
GET  /api/jobs              → 任务列表（读 states/ 目录）
POST /api/jobs              → 提交新爬虫任务（后台运行）
GET  /api/knowledge         → 知识库统计（读 knowledge.json）
```

**Dashboard 页面区块：**
1. **顶部统计卡片**: 总任务数、通过率、平均分数、知识库 URL 数
2. **新任务表单**: URL + keyword + source 选择 + 提交按钮 (HTMX POST)
3. **任务列表**: 表格显示最近任务，状态用颜色标签

**Step 1: Create web/api.py**
```python
"""API routes for the dashboard."""
import json
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse

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
async def get_knowledge():
    k_path = DATA_DIR / "knowledge.json"
    if k_path.exists():
        return json.loads(k_path.read_text())
    return {"crawled_urls": [], "site_patterns": {}, "prompt_stats": {}}


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
```

**Step 2: Register router in web/app.py**
```python
from web.api import router
app.include_router(router)
```

**Step 3: Build dashboard HTML with HTMX**
```html
{% extends "base.html" %}
{% block content %}
<div class="max-w-7xl mx-auto p-6">
    <h1 class="text-3xl font-bold mb-8">🕷️ AI Crawler v2</h1>
    
    <!-- Stats Cards -->
    <div id="stats" hx-get="/api/knowledge" hx-trigger="load" hx-swap="innerHTML"
         class="grid grid-cols-4 gap-4 mb-8">
        <div class="bg-gray-900 rounded-lg p-4">
            <div class="text-gray-400 text-sm">Crawled URLs</div>
            <div class="text-2xl font-bold" id="stat-urls">—</div>
        </div>
        <div class="bg-gray-900 rounded-lg p-4">
            <div class="text-gray-400 text-sm">Site Patterns</div>
            <div class="text-2xl font-bold" id="stat-patterns">—</div>
        </div>
        <div class="bg-gray-900 rounded-lg p-4">
            <div class="text-gray-400 text-sm">Avg Score</div>
            <div class="text-2xl font-bold" id="stat-score">—</div>
        </div>
        <div class="bg-gray-900 rounded-lg p-4">
            <div class="text-gray-400 text-sm">Failures</div>
            <div class="text-2xl font-bold" id="stat-failures">—</div>
        </div>
    </div>

    <!-- New Job Form -->
    <div class="bg-gray-900 rounded-lg p-6 mb-8">
        <h2 class="text-xl font-semibold mb-4">New Crawl Job</h2>
        <form hx-post="/api/jobs" hx-swap="none" class="flex gap-4 items-end">
            <div class="flex-1">
                <label class="block text-sm text-gray-400 mb-1">URL</label>
                <input name="url" type="url" placeholder="https://youtube.com/watch?v=..."
                       class="w-full bg-gray-800 rounded px-3 py-2 text-gray-100">
            </div>
            <div class="w-48">
                <label class="block text-sm text-gray-400 mb-1">Keyword</label>
                <input name="keyword" type="text" placeholder="hiking tips"
                       class="w-full bg-gray-800 rounded px-3 py-2 text-gray-100">
            </div>
            <div class="w-32">
                <label class="block text-sm text-gray-400 mb-1">Source</label>
                <select name="source" class="w-full bg-gray-800 rounded px-3 py-2 text-gray-100">
                    <option value="youtube">YouTube</option>
                    <option value="web">Web</option>
                    <option value="reddit">Reddit</option>
                </select>
            </div>
            <button type="submit" class="bg-blue-600 hover:bg-blue-700 rounded px-6 py-2 font-medium">
                🚀 Crawl
            </button>
        </form>
    </div>

    <!-- Jobs Table -->
    <div class="bg-gray-900 rounded-lg p-6">
        <h2 class="text-xl font-semibold mb-4">Recent Jobs</h2>
        <div hx-get="/api/jobs" hx-trigger="load, every 10s" hx-swap="innerHTML" id="jobs-table">
            <p class="text-gray-500">Loading...</p>
        </div>
    </div>
</div>
{% endblock %}
```

**Step 4: Commit**
```bash
git add web/
git commit -m "feat: dashboard API + job management UI"
```

**Acceptance Criteria:**
1. GET /api/jobs 返回任务列表
2. POST /api/jobs 提交新任务（后台运行）
3. GET /api/knowledge 返回知识库统计
4. Dashboard 页面显示统计卡片 + 新任务表单 + 任务列表
5. HTMX 实现无刷新更新

---

### Task 7: Dashboard — 文章预览 + 知识库面板

**Objective:** 预览生成的 HTML 文章，查看知识库数据。

**Files:**
- Modify: `web/api.py` — add article/knowledge endpoints
- Modify: `web/templates/dashboard.html` — add panels

**Step 1: Add API endpoints**
```python
from fastapi.responses import FileResponse

@router.get("/articles")
async def list_articles():
    output_dir = DATA_DIR / "output"
    articles = []
    if output_dir.exists():
        for f in sorted(output_dir.glob("*.html"), reverse=True):
            articles.append({"name": f.name})
    return {"articles": articles}

@router.get("/articles/{name}")
async def get_article(name: str):
    path = DATA_DIR / "output" / name
    if path.exists():
        return FileResponse(path, media_type="text/html")
    return JSONResponse({"error": "not found"}, status_code=404)
```

**Step 2: Add knowledge panel and article list to dashboard**
- Knowledge panel: site_patterns table, prompt_stats, failure_log
- Article list: links that open in new tab or iframe

**Step 3: Commit**
```bash
git add web/
git commit -m "feat: article preview + knowledge management panel"
```

**Acceptance Criteria:**
1. /api/articles 列出所有生成的文章
2. /api/articles/{name} 返回 HTML 文件
3. Dashboard 显示文章列表和知识库面板

---

### Task 8: 端到端测试 + 文档更新

**Objective:** 确保所有改动协调工作，更新 ARCHITECTURE.md。

**Files:**
- Modify: `ARCHITECTURE.md`

**Step 1: Full test suite**
```bash
cd /home/hermes/ai-crawler-v2 && python -m pytest tests/ -v
```

**Step 2: Smoke test the dashboard**
```bash
cd /home/hermes/ai-crawler-v2 && python -c "from web.app import app; print('FastAPI app loads OK')"
```

**Step 3: Update ARCHITECTURE.md**
- Add web/ to directory structure
- Document new API endpoints
- Document new constants in context.py
- Document failure_report field
- Update Factor #3, #4, #6, #7, #13 sections

**Step 4: Commit**
```bash
git add ARCHITECTURE.md tests/
git commit -m "docs: update architecture for dashboard + 12-Factor improvements"
```

**Acceptance Criteria:**
1. 全部测试通过
2. FastAPI app 能正常加载
3. ARCHITECTURE.md 反映最新结构

---

## Execution Order

```
Phase 1: Core Improvements
  Task 1 (context constants) → Task 2 (shared parser) → Task 3 (WAL) → Task 4 (failure + patterns)

Phase 2: Web Dashboard
  Task 5 (FastAPI skeleton) → Task 6 (API + UI) → Task 7 (preview + knowledge) → Task 8 (E2E + docs)
```

Phase 1 must complete before Phase 2 starts. Each task depends on the previous one.
