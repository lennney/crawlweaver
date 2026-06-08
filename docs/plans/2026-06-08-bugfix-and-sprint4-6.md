# AI Crawler v2 — Bug Fix + Sprint 4-6 Plan

> **For Hermes:** Use code-with-review-hook skill to implement this plan task-by-task.

**Goal:** 修复 14 个已知 bug，然后实现知识库自进化、多源扩展、部署上线。

**Architecture:** 12-Factor Agents，reducer 纯函数控制流，FastAPI + HTMX dashboard。

**Tech Stack:** Python 3.12, FastAPI, Jinja2, httpx, threading.Lock

---

## Phase 1: Critical + Important Bug Fixes

### Task 1: Path Traversal Fix in `/api/articles/{name}`

**Objective:** 防止路径遍历攻击，限制只能访问 output 目录内的文件。

**Files:**
- Modify: `web/api.py:215`

**Fix:**
```python
# In GET /api/articles/{name}:
if "/" in name or "\\" in name or ".." in name:
    return JSONResponse({"error": "invalid name"}, status_code=400)
path = (DATA_DIR / "output" / name).resolve()
if not path.is_relative_to((DATA_DIR / "output").resolve()):
    return JSONResponse({"error": "forbidden"}, status_code=403)
```

**Test:** `tests/test_web.py` — 新增 test_path_traversal_blocked
```python
async def test_path_traversal_blocked():
    """GET /api/articles/../../etc/passwd should return 400."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/articles/../../etc/passwd")
        assert resp.status_code in (400, 404)
```

**Acceptance:**
1. `../../etc/passwd` 返回 400
2. `normal-article.html` 正常返回
3. 测试通过

---

### Task 2: Jinja2 autoescape=True

**Objective:** 修复 XSS 漏洞，Jinja2 启用自动转义。

**Files:**
- Modify: `tools/render.py:40`

**Fix:**
```python
# Change autoescape=False to autoescape=True
env = Environment(
    loader=FileSystemLoader(str(templates_dir)),
    autoescape=True,  # was False
)
```

注意：`sections_html` 是预渲染的 HTML，需要用 `Markup()` 包装。在模板中用 `{{ sections_html | safe }}` 或在传入前用 `Markup()` 标记。

**Test:** 验证现有测试仍然通过（render 输出不应变化，因为内容本身不含 HTML 特殊字符）。

---

### Task 3: Thread-safe knowledge.json reads

**Objective:** 所有 knowledge.json 读取都通过 lock 保护。

**Files:**
- Modify: `knowledge.py` — 给 `load_knowledge` 加锁
- Modify: `web/api.py` — 所有读取改用 `load_knowledge()`

**Fix (knowledge.py):**
```python
def load_knowledge(path: Path | None = None) -> Knowledge:
    """Load knowledge with thread-safe lock."""
    p = path or KNOWLEDGE_PATH
    with _knowledge_lock:
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                return Knowledge(**data)
            except Exception:
                return Knowledge()
        return Knowledge()
```

**Fix (web/api.py):**
替换所有 `json.loads(k_path.read_text())` 为 `load_knowledge(k_path)`。

---

### Task 4: Thread-safe state file approve/reject

**Objective:** approve/reject 操作使用原子读-改-写。

**Files:**
- Modify: `web/api.py` — approve_article, reject_article

**Fix:**
```python
import fcntl

def _atomic_update_state(state_path: Path, update_fn):
    """Atomic read-modify-write with file lock."""
    with open(state_path, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            data = json.loads(f.read())
            update_fn(data)
            f.seek(0)
            f.truncate()
            json.dump(data, f, indent=2, ensure_ascii=False)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
```

---

### Task 5: Deprecated on_event → lifespan

**Objective:** 替换 FastAPI deprecated on_event 为 lifespan context manager。

**Files:**
- Modify: `web/app.py`

**Fix:**
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    task_queue.set_handler(make_crawl_handler())
    yield

app = FastAPI(title="AI Crawler v2", lifespan=lifespan)
```

---

### Task 6: File handle leak in extract.py

**Objective:** 修复 open() without context manager。

**Files:**
- Modify: `tools/extract.py:97`

**Fix:**
```python
# Before: raw = open(subs[0]).read()
# After:
raw = Path(subs[0]).read_text(encoding="utf-8")
```

---

### Task 7: Silent exception swallowing → logging

**Objective:** 所有 except Exception 块至少 log 一条 warning。

**Files:**
- Modify: `web/api.py:61,124,313,411`
- Modify: `llm.py:70`

**Fix pattern:**
```python
import logging
logger = logging.getLogger(__name__)

# Before:
except Exception:
    pass

# After:
except Exception:
    logger.warning("Failed to [context]", exc_info=True)
```

---

### Task 8: SEO_PROMPT lazy loading

**Objective:** 延迟加载 SEO prompt，避免 import 时副作用。

**Files:**
- Modify: `tools/seo.py:15-16`

**Fix:**
```python
_seo_prompt_cache: str | None = None

def _get_seo_prompt() -> str:
    global _seo_prompt_cache
    if _seo_prompt_cache is None:
        prompt_path = Path(__file__).parent.parent / "prompts" / "seo.md"
        _seo_prompt_cache = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else DEFAULT_SEO_PROMPT
    return _seo_prompt_cache
```

---

## Phase 2: Minor Bug Fixes

### Task 9: Deterministic hash for state filenames

**Files:** `cli.py:140`
**Fix:** `hashlib.md5(url.encode()).hexdigest()[:6]` 替代 `hash(url) & 0xFFFFFF`

### Task 10: RSS base_url from env

**Files:** `publisher.py`, `web/api.py`
**Fix:** `base_url = os.environ.get("CRAWLER_BASE_URL", "https://example.com")`

### Task 11: Atomic knowledge.json writes

**Files:** `knowledge.py`
**Fix:** write to temp file → `os.rename()` (atomic on Linux)

---

## Phase 3: Sprint 4 — 知识库自进化

### Task 12: SitePattern 自动优化提取策略

**Objective:** 根据 site_patterns 的 avg_quality 自动选择最佳 extractor 和 prompt。

**Files:**
- Modify: `reducer.py` — extract 步骤查 site_patterns
- Modify: `knowledge.py` — get_best_strategy(domain)

**Logic:**
```python
# In reducer, before calling extract:
pattern = knowledge.get_best_strategy(domain)
if pattern and pattern.sample_count >= 3:
    # Use historical best extractor/prompt
    extractor = pattern.extractor
    prompt = pattern.best_prompt
else:
    # Default strategy
    extractor, prompt = default_strategy(url)
```

### Task 13: 失败模式自动规避

**Objective:** 记录失败原因，下次遇到相同域名/错误模式时自动跳过或换策略。

**Files:**
- Modify: `knowledge.py` — should_skip(url) 方法
- Modify: `reducer.py` — extract 前检查

---

## Phase 4: Sprint 5 — 多源扩展

### Task 14: Twitter/X 提取器

**Objective:** 支持从 X/Twitter 提取推文内容。

**Files:**
- Create: `tools/extractors/twitter.py`
- Modify: `tools/extract.py` — 添加 twitter 路由

### Task 15: 微信公众号提取器

**Objective:** 支持从微信公众号文章提取内容。

**Files:**
- Create: `tools/extractors/wechat.py`
- Modify: `tools/extract.py` — 添加 wechat 路由

### Task 16: 知乎提取器

**Objective:** 支持从知乎回答/文章提取内容。

**Files:**
- Create: `tools/extractors/zhihu.py`
- Modify: `tools/extract.py` — 添加 zhihu 路由

---

## Phase 5: Sprint 6 — 部署上线

### Task 17: Docker 化

**Objective:** Dockerfile + docker-compose.yml，一键部署。

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

### Task 18: Cron 定时爬取

**Objective:** 支持定时任务自动爬取关键词列表。

**Files:**
- Modify: `cli.py` — 添加 `cron` 子命令
- Create: `cron_config.yaml`

### Task 19: 个人站部署脚本

**Objective:** 一键部署到 VPS，nginx 反代 + SSL。

**Files:**
- Create: `scripts/deploy.sh`

---

## Execution Order

```
Phase 1 (Tasks 1-8): Critical + Important bugs  ← 先做
Phase 2 (Tasks 9-11): Minor bugs
Phase 3 (Tasks 12-13): Sprint 4 知识库自进化
Phase 4 (Tasks 14-16): Sprint 5 多源扩展
Phase 5 (Tasks 17-19): Sprint 6 部署上线
```

## Total Estimated Time
- Phase 1-2: ~1.5 hours (bug fixes)
- Phase 3: ~1 hour (self-evolution)
- Phase 4: ~2 hours (multi-source)
- Phase 5: ~1.5 hours (deployment)
- **Total: ~6 hours**
