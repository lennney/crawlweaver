# Sprint 1: 批量处理 + 关键词覆盖

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 让 AI Crawler 从"一次一个URL"升级为"批量内容工厂"，支持任务队列、CSV批量导入、关键词覆盖追踪。

**Architecture:** 
- TaskQueue 用 threading.Semaphore 控制并发，Job 用 dataclass，队列用内存 dict
- 文件名 `task_queue.py`（避免和 Python stdlib `queue` 冲突）
- Batch import 从 CSV 解析后逐条入队
- Keyword coverage 作为 Knowledge 的新维度，reducer 自动记录

**Tech Stack:** Python 3.11, threading, csv, FastAPI, HTMX

---

## Feature 1: Task Queue（任务队列 + 并发控制）

### Task 1: Job 模型 + TaskQueue 核心

**Objective:** 创建 Job 数据模型和带并发控制的任务队列。

**Files:**
- Create: `task_queue.py`（注意不是 `queue.py`，避免和 stdlib 冲突）
- Create: `tests/test_task_queue.py`

**Step 1: Write failing test**
```python
# tests/test_task_queue.py
"""Tests for task queue — concurrency control and job tracking."""
import time
import threading
from task_queue import TaskQueue, JobStatus


def test_job_status_enum():
    """Job should have pending/running/completed/failed states."""
    assert JobStatus.PENDING == "pending"
    assert JobStatus.RUNNING == "running"
    assert JobStatus.COMPLETED == "completed"
    assert JobStatus.FAILED == "failed"


def test_submit_job():
    """Submitting a job should return a job ID and store it."""
    tq = TaskQueue(max_workers=1)
    job_id = tq.submit(url="https://example.com", keyword="test", source="web")
    assert isinstance(job_id, str)
    assert len(job_id) > 0
    job = tq.get_job(job_id)
    assert job.url == "https://example.com"
    assert job.keyword == "test"
    assert job.status == JobStatus.PENDING


def test_list_jobs():
    """Should list all jobs sorted by creation time."""
    tq = TaskQueue(max_workers=1)
    tq.submit(url="https://a.com", keyword="a", source="web")
    tq.submit(url="https://b.com", keyword="b", source="web")
    jobs = tq.list_jobs()
    assert len(jobs) == 2


def test_max_workers_limits_concurrency():
    """Should not run more than max_workers jobs simultaneously."""
    tq = TaskQueue(max_workers=1)
    running = []
    max_concurrent = []
    lock = threading.Lock()

    def slow_task(job):
        with lock:
            running.append(job.id)
            max_concurrent.append(len(running))
        time.sleep(0.2)
        with lock:
            running.remove(job.id)

    tq.set_handler(slow_task)
    tq.submit(url="https://a.com", keyword="a", source="web")
    tq.submit(url="https://b.com", keyword="b", source="web")
    time.sleep(0.5)

    assert max(max_concurrent) <= 1


def test_job_completed_status():
    """After handler runs, job should be completed."""
    tq = TaskQueue(max_workers=1)

    def handler(job):
        job.result = {"score": 85}

    tq.set_handler(handler)
    job_id = tq.submit(url="https://a.com", keyword="a", source="web")
    time.sleep(0.5)

    job = tq.get_job(job_id)
    assert job.status == JobStatus.COMPLETED
    assert job.result == {"score": 85}


def test_job_failed_status():
    """If handler raises, job should be failed with error."""
    tq = TaskQueue(max_workers=1)

    def bad_handler(job):
        raise RuntimeError("LLM exploded")

    tq.set_handler(bad_handler)
    job_id = tq.submit(url="https://a.com", keyword="a", source="web")
    time.sleep(0.5)

    job = tq.get_job(job_id)
    assert job.status == JobStatus.FAILED
    assert "LLM exploded" in job.error
```

**Step 2: Run test to verify failure**
Run: `cd /home/hermes/ai-crawler-v2 && python -m pytest tests/test_task_queue.py -v`
Expected: FAIL (module doesn't exist)

**Step 3: Write implementation**
```python
# task_queue.py
"""Task Queue — concurrent job execution with backpressure.

Factor #8: Own your control flow. No Celery, no Redis.
Just threading.Semaphore + a dict of jobs.
"""
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger("crawler.queue")


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    url: str
    keyword: str
    source: str
    content_type: str = "Beginner Guide"
    status: JobStatus = JobStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    result: Any = None
    error: str = ""


class TaskQueue:
    """Simple concurrent task queue with semaphore-based backpressure.

    Usage:
        tq = TaskQueue(max_workers=2)
        tq.set_handler(my_crawl_function)  # handler(job: Job)
        job_id = tq.submit(url="...", keyword="...", source="youtube")
    """

    def __init__(self, max_workers: int = 2):
        self.max_workers = max_workers
        self._semaphore = threading.Semaphore(max_workers)
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._handler: Optional[Callable[[Job], None]] = None

    def set_handler(self, handler: Callable[[Job], None]):
        """Set the function that processes each job."""
        self._handler = handler

    def submit(self, url: str, keyword: str, source: str = "youtube",
               content_type: str = "Beginner Guide") -> str:
        """Submit a job. Returns job ID."""
        job_id = uuid.uuid4().hex[:12]
        job = Job(
            id=job_id, url=url, keyword=keyword,
            source=source, content_type=content_type,
        )
        with self._lock:
            self._jobs[job_id] = job

        t = threading.Thread(target=self._run, args=(job,), daemon=True)
        t.start()

        logger.info(f"Job submitted: {job_id} ({keyword})")
        return job_id

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, limit: int = 50) -> list[Job]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
            return jobs[:limit]

    def stats(self) -> dict:
        """Return queue statistics."""
        with self._lock:
            counts = {"pending": 0, "running": 0, "completed": 0, "failed": 0}
            for j in self._jobs.values():
                counts[j.status.value] = counts.get(j.status.value, 0) + 1
            return counts

    def _run(self, job: Job):
        """Worker thread: wait for semaphore, run handler."""
        self._semaphore.acquire()
        try:
            with self._lock:
                job.status = JobStatus.RUNNING
                job.started_at = time.time()

            if self._handler:
                self._handler(job)

            with self._lock:
                job.status = JobStatus.COMPLETED
                job.finished_at = time.time()
            logger.info(f"Job completed: {job.id} ({job.keyword})")

        except Exception as e:
            with self._lock:
                job.status = JobStatus.FAILED
                job.error = str(e)
                job.finished_at = time.time()
            logger.error(f"Job failed: {job.id} — {e}")

        finally:
            self._semaphore.release()
```

**Step 4: Run test to verify pass**
Run: `cd /home/hermes/ai-crawler-v2 && python -m pytest tests/test_task_queue.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add task_queue.py tests/test_task_queue.py
git commit -m "feat: TaskQueue with semaphore-based concurrency control"
```

**Acceptance Criteria:**
1. `task_queue.py` 文件名（不是 queue.py）
2. TaskQueue(max_workers=N) 限制同时运行的任务数
3. submit() 返回 job_id，get_job() 查状态
4. list_jobs() 按创建时间倒序，stats() 返回计数
5. handler 异常不会崩溃队列，job 标记为 FAILED
6. 6 个测试全过

---

### Task 2: 接入 Dashboard API

**Objective:** 把 TaskQueue 接入 FastAPI，替换 BackgroundTasks。

**Files:**
- Modify: `web/app.py` — 创建全局 task_queue，startup 设置 handler
- Modify: `web/api.py` — 替换 _run_crawl 为 _run_crawl_job，注入 task_queue
- Modify: `web/templates/dashboard.html` — stats 加队列信息
- Modify: `tests/test_web.py` — 更新 POST /api/jobs 测试

**Step 1: Update web/app.py**

在现有代码顶部 import 后、app 创建前添加：
```python
from task_queue import TaskQueue

task_queue = TaskQueue(max_workers=2)
```

在 app 创建后添加 startup 事件：
```python
@app.on_event("startup")
async def startup():
    """Initialize task queue handler."""
    from web.api import make_crawl_handler
    task_queue.set_handler(make_crawl_handler())
```

**Step 2: Update web/api.py**

在文件顶部 import 区添加：
```python
from task_queue import Job, JobStatus, TaskQueue
```

将模块顶部的 `router = APIRouter(prefix="/api")` 之后添加 task_queue 引用：
```python
# Will be set by app.py at import time
_task_queue: "TaskQueue | None" = None

def get_queue() -> "TaskQueue":
    global _task_queue
    if _task_queue is None:
        from web.app import task_queue as tq
        _task_queue = tq
    return _task_queue
```

替换 `create_job` 函数：
```python
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
```

替换 `list_jobs` 函数：
```python
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
```

删除旧的 `_run_crawl` 函数，替换为：
```python
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
```

**Step 3: Update tests/test_web.py**

添加 POST /api/jobs 测试：
```python
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
```

**Step 4: Commit**
```bash
git add web/app.py web/api.py web/templates/dashboard.html tests/test_web.py
git commit -m "feat: integrate TaskQueue into dashboard API"
```

**Acceptance Criteria:**
1. web/app.py 创建全局 task_queue，startup 设置 handler
2. POST /api/jobs 通过 task_queue.submit() 提交
3. GET /api/jobs 显示队列统计（pending/running/completed/failed）+ 任务表格
4. _run_crawl 替换为 make_crawl_handler()
5. 新增 POST /api/jobs 测试通过
6. 全部测试通过

---

## Feature 2: Batch Import（批量导入）

### Task 3: CLI batch 命令

**Objective:** `python cli.py batch urls.csv` 从 CSV 批量提交任务。

**Files:**
- Modify: `cli.py` — 添加 batch 子命令和 parse_batch_csv
- Create: `tests/test_batch.py`
- Create: `examples/batch_example.csv`

**Step 1: Write failing test**
```python
# tests/test_batch.py
"""Tests for batch CSV import."""
import tempfile
import os


def test_parse_csv():
    """Should parse CSV with url, keyword, source columns."""
    from cli import parse_batch_csv

    csv_content = "url,keyword,source\nhttps://a.com,test a,web\nhttps://b.com,test b,youtube\n"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write(csv_content)
        f.flush()
        rows = parse_batch_csv(f.name)
    os.unlink(f.name)

    assert len(rows) == 2
    assert rows[0]["url"] == "https://a.com"
    assert rows[0]["keyword"] == "test a"
    assert rows[0]["source"] == "web"
    assert rows[1]["source"] == "youtube"


def test_parse_csv_defaults():
    """Missing source/content_type should use defaults."""
    from cli import parse_batch_csv

    csv_content = "url,keyword\nhttps://a.com,test\n"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write(csv_content)
        f.flush()
        rows = parse_batch_csv(f.name)
    os.unlink(f.name)

    assert rows[0]["source"] == "youtube"
    assert rows[0]["content_type"] == "Beginner Guide"


def test_parse_csv_empty():
    """Empty CSV should return empty list."""
    from cli import parse_batch_csv

    csv_content = "url,keyword\n"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write(csv_content)
        f.flush()
        rows = parse_batch_csv(f.name)
    os.unlink(f.name)

    assert rows == []
```

**Step 2: Run test to verify failure**
Run: `cd /home/hermes/ai-crawler-v2 && python -m pytest tests/test_batch.py -v`
Expected: FAIL (parse_batch_csv doesn't exist)

**Step 3: Implement in cli.py**

在文件顶部 import 区添加 `import csv`。

在 `cmd_knowledge` 函数之后添加：
```python
def parse_batch_csv(path: str) -> list[dict]:
    """Parse batch CSV file. Required columns: url, keyword.
    Optional: source (default youtube), content_type (default Beginner Guide).
    """
    rows = []
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get("url", "").strip()
            if not url:
                continue
            rows.append({
                "url": url,
                "keyword": row.get("keyword", "").strip(),
                "source": row.get("source", "youtube").strip() or "youtube",
                "content_type": row.get("content_type", "Beginner Guide").strip() or "Beginner Guide",
            })
    return rows
```

在 argparse 部分添加 batch 子命令（在 dashboard 子命令之后）：
```python
p_batch = sub.add_parser("batch", help="Batch import from CSV")
p_batch.add_argument("csv", help="CSV file (columns: url, keyword, source)")
p_batch.add_argument("--knowledge", default="knowledge.json")
p_batch.add_argument("--max-workers", type=int, default=2)
```

在 if/elif 链中添加：
```python
elif args.command == "batch":
    cmd_batch(args)
```

实现 cmd_batch：
```python
def cmd_batch(args):
    """Batch import from CSV."""
    rows = parse_batch_csv(args.csv)
    if not rows:
        print("No valid rows in CSV")
        return

    print(f"Loaded {len(rows)} jobs from {args.csv}")
    for i, row in enumerate(rows, 1):
        print(f"  [{i}] {row['keyword']} → {row['url']}")

    from task_queue import TaskQueue

    def crawl_handler(job):
        from state import make_state
        from knowledge import load_knowledge, save_knowledge
        from llm import LLM
        from reducer import crawl as run_crawl

        state = make_state(url=job.url, source=job.source, keyword=job.keyword)
        knowledge = load_knowledge(args.knowledge)
        llm = LLM()
        state = run_crawl(state, knowledge, llm)
        save_knowledge(knowledge, args.knowledge)
        job.result = {"step": state.step.value}

    tq = TaskQueue(max_workers=args.max_workers)
    tq.set_handler(crawl_handler)
    for row in rows:
        tq.submit(**row)

    # Wait for all to finish
    import time
    while True:
        stats = tq.stats()
        if stats["pending"] == 0 and stats["running"] == 0:
            break
        time.sleep(1)

    # Summary
    stats = tq.stats()
    print(f"\nBatch complete: {stats['completed']} passed, {stats['failed']} failed out of {len(rows)}")
```

**Step 4: Create example CSV**
```csv
# examples/batch_example.csv
url,keyword,source,content_type
https://youtube.com/watch?v=example1,hiking tips for beginners,youtube,Beginner Guide
https://example.com/article,web scraping tutorial,web,Tutorial
```

**Step 5: Commit**
```bash
git add cli.py tests/test_batch.py examples/batch_example.csv
git commit -m "feat: batch CSV import via CLI"
```

**Acceptance Criteria:**
1. `python cli.py batch urls.csv` 解析 CSV 并用 TaskQueue 提交
2. parse_batch_csv 正确处理缺失列的默认值
3. 并发控制（max_workers 默认 2）
4. 完成后输出汇总（completed/failed）
5. 3 个测试全过

---

### Task 4: Dashboard Batch Import

**Objective:** Dashboard 加 CSV 上传按钮，支持批量导入。

**Files:**
- Modify: `web/api.py` — add POST /api/batch
- Modify: `web/templates/dashboard.html` — add upload form
- Modify: `tests/test_web.py` — add test

**Step 1: Add API endpoint to web/api.py**
```python
import csv
from io import StringIO

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
```

**Step 2: Add upload form to dashboard.html**

在 New Job Form 的 `</div>` 之后、Jobs Table 之前添加：
```html
<!-- Batch Import -->
<div class="bg-gray-900 rounded-lg p-6 mb-8">
    <h2 class="text-xl font-semibold mb-4">📋 Batch Import</h2>
    <form hx-post="/api/batch" hx-encoding="multipart/form-data"
          hx-target="#batch-result" class="flex gap-4 items-end">
        <div class="flex-1">
            <input name="file" type="file" accept=".csv"
                   class="w-full bg-gray-800 rounded px-3 py-2 text-gray-100 text-sm">
        </div>
        <button type="submit" class="bg-green-600 hover:bg-green-700 rounded px-6 py-2 font-medium">
            📤 Import CSV
        </button>
    </form>
    <div id="batch-result" class="mt-2 text-sm"></div>
</div>
```

**Step 3: Add test**
```python
@pytest.mark.asyncio
async def test_batch_import_no_file():
    """POST /api/batch without file should return 400."""
    from httpx import AsyncClient, ASGITransport
    from web.app import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/batch")
        assert resp.status_code == 400
```

**Step 4: Commit**
```bash
git add web/api.py web/templates/dashboard.html tests/test_web.py
git commit -m "feat: dashboard batch CSV upload"
```

**Acceptance Criteria:**
1. POST /api/batch 接受 multipart CSV 文件
2. 解析后逐条入 TaskQueue
3. Dashboard 显示上传表单和结果反馈
4. 无文件时返回 400
5. 测试通过

---

## Feature 3: Keyword Coverage（关键词覆盖追踪）

### Task 5: KeywordCoverage 模型

**Objective:** 在 Knowledge 中追踪关键词覆盖状态。

**Files:**
- Modify: `knowledge.py` — 添加 KeywordCoverage 模型和方法
- Create: `tests/test_coverage.py`

**Step 1: Write failing test**
```python
# tests/test_coverage.py
"""Tests for keyword coverage tracking."""
from knowledge import Knowledge, KeywordCoverage


def test_record_keyword_coverage():
    """Should record keyword as covered after successful crawl."""
    k = Knowledge()
    k.record_coverage("hiking tips", "https://a.com/article", score=85)
    assert "hiking tips" in k.keyword_coverage
    cov = k.keyword_coverage["hiking tips"]
    assert cov.covered is True
    assert cov.article_url == "https://a.com/article"
    assert cov.score == 85


def test_coverage_summary():
    """Should return covered/uncovered counts."""
    k = Knowledge()
    k.record_coverage("hiking tips", "https://a.com", score=85)
    k.record_coverage("camping gear", "https://b.com", score=72)
    k.add_target_keyword("backpacking")

    summary = k.coverage_summary()
    assert summary["covered"] == 2
    assert summary["targeted"] == 1
    assert summary["total_keywords"] == 3


def test_add_target_keyword():
    """Adding a target keyword should mark it as uncovered."""
    k = Knowledge()
    k.add_target_keyword("python tutorial")
    assert "python tutorial" in k.keyword_coverage
    assert k.keyword_coverage["python tutorial"].covered is False


def test_coverage_not_duplicated():
    """Recording same keyword twice should update, not duplicate."""
    k = Knowledge()
    k.record_coverage("hiking", "https://a.com", score=80)
    k.record_coverage("hiking", "https://b.com", score=90)
    assert len(k.keyword_coverage) == 1
    assert k.keyword_coverage["hiking"].score == 90


def test_coverage_json_roundtrip():
    """Coverage should survive JSON serialization."""
    import tempfile, os
    from knowledge import save_knowledge, load_knowledge

    k = Knowledge()
    k.record_coverage("test", "https://a.com", score=80)
    k.add_target_keyword("uncovered")

    path = tempfile.mktemp(suffix=".json")
    save_knowledge(k, path)
    k2 = load_knowledge(path)
    os.unlink(path)

    assert "test" in k2.keyword_coverage
    assert k2.keyword_coverage["test"].covered is True
    assert k2.keyword_coverage["test"].score == 80
    assert "uncovered" in k2.keyword_coverage
    assert k2.keyword_coverage["uncovered"].covered is False
```

**Step 2: Run test to verify failure**
Run: `cd /home/hermes/ai-crawler-v2 && python -m pytest tests/test_coverage.py -v`
Expected: FAIL (KeywordCoverage doesn't exist)

**Step 3: Implement in knowledge.py**

在 SitePattern 类之后添加：
```python
class KeywordCoverage(BaseModel):
    keyword: str = ""
    covered: bool = False
    article_url: str = ""
    score: int = 0
    covered_at: str = ""
```

在 Knowledge 类中添加字段（在 prompt_stats 之后）：
```python
keyword_coverage: dict[str, KeywordCoverage] = Field(default_factory=dict)
```

在 Knowledge 类中添加方法（在 failure_count 之后）：
```python
def record_coverage(self, keyword: str, article_url: str, score: int):
    """Record that a keyword has been covered."""
    self.keyword_coverage[keyword] = KeywordCoverage(
        keyword=keyword,
        covered=True,
        article_url=article_url,
        score=score,
        covered_at=datetime.now().isoformat(),
    )

def add_target_keyword(self, keyword: str):
    """Add a target keyword (not yet covered)."""
    if keyword not in self.keyword_coverage:
        self.keyword_coverage[keyword] = KeywordCoverage(
            keyword=keyword, covered=False,
        )

def coverage_summary(self) -> dict:
    covered = sum(1 for c in self.keyword_coverage.values() if c.covered)
    targeted = sum(1 for c in self.keyword_coverage.values() if not c.covered)
    return {"covered": covered, "targeted": targeted, "total_keywords": len(self.keyword_coverage)}
```

**Step 4: Run test to verify pass**
Run: `cd /home/hermes/ai-crawler-v2 && python -m pytest tests/test_coverage.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add knowledge.py tests/test_coverage.py
git commit -m "feat: keyword coverage tracking in Knowledge"
```

**Acceptance Criteria:**
1. KeywordCoverage 模型含 keyword/covered/article_url/score/covered_at
2. record_coverage() 标记关键词为已覆盖（可更新）
3. add_target_keyword() 添加待覆盖关键词（不覆盖已有的）
4. coverage_summary() 返回 covered/targeted/total_keywords
5. JSON 序列化/反序列化不丢数据
6. 5 个测试全过

---

### Task 6: Reducer 自动记录覆盖 + Dashboard 覆盖面板

**Objective:** reducer PASSED 后自动记录关键词覆盖，Dashboard 显示覆盖面板。

**Files:**
- Modify: `reducer.py` — PASSED 后调用 record_coverage
- Modify: `web/api.py` — add GET /api/coverage
- Modify: `web/templates/dashboard.html` — add coverage panel
- Modify: `tests/test_web.py` — add coverage test

**Step 1: Update reducer.py**

在 PASSED 分支中，`knowledge.record_site_pattern(...)` 之后添加：
```python
# Record keyword coverage
if state.keyword:
    knowledge.record_coverage(
        keyword=state.keyword,
        article_url=state.html_path or state.url,
        score=state.verify.score if state.verify else 0,
    )
```

**Step 2: Add API endpoint to web/api.py**

在 `get_article` 函数之后添加：
```python
@router.get("/coverage")
async def get_coverage():
    """HTMX: return keyword coverage HTML panel."""
    k_path = DATA_DIR / "knowledge.json"
    if not k_path.exists():
        return HTMLResponse("<p class='text-gray-500'>No data yet.</p>")

    data = json.loads(k_path.read_text())
    coverage = data.get("keyword_coverage", {})

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
```

**Step 3: Add coverage panel to dashboard.html**

在 Knowledge Panel 的 `</div>` 之后添加：
```html
<!-- Keyword Coverage -->
<div class="bg-gray-900 rounded-lg p-6 mt-8">
    <h2 class="text-xl font-semibold mb-4">🎯 Keyword Coverage</h2>
    <div hx-get="/api/coverage" hx-trigger="load" hx-swap="innerHTML" id="coverage-panel">
        <p class="text-gray-500">Loading...</p>
    </div>
</div>
```

**Step 4: Add test**
```python
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
```

**Step 5: Commit**
```bash
git add reducer.py web/api.py web/templates/dashboard.html tests/test_web.py
git commit -m "feat: auto-record keyword coverage + dashboard panel"
```

**Acceptance Criteria:**
1. reducer PASSED 后自动调用 record_coverage（在 record_site_pattern 之后）
2. GET /api/coverage 返回 HTML（✅ covered 表格 + ⏳ uncovered 标签）
3. Dashboard 显示覆盖面板
4. 覆盖率统计（✅ N covered | ⏳ N targeted）
5. 测试通过

---

## Execution Order

```
Task 1 (Job模型 + TaskQueue) 
  ↓
Task 2 (接入Dashboard API) 
  ↓
Task 3 (CLI batch 命令)
  ↓
Task 4 (Dashboard batch 上传)
  ↓
Task 5 (Coverage 模型)
  ↓
Task 6 (Reducer + Dashboard 覆盖面板)
```

每个 Task 依赖前一个。Feature 1 (Task 1-2) → Feature 2 (Task 3-4) → Feature 3 (Task 5-6)。
