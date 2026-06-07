# Sprint 2+3: 审核 + 成本 + 质量趋势 + 发布

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 补全内容工厂的后半段：人工审核 → 成本可见 → 质量趋势 → 静态站发布。

**参考模式：**
- Frase 6-stage: Research→Strategy→Write→Audit→Monitor→Fix（我们覆盖 Write→Audit→Monitor）
- ContentCreationWorkflow: step_review gate between verify and publish
- Production agents: cost metering per LLM call (token tracking)

**Tech Stack:** Python 3.11, FastAPI, HTMX, tiktoken (估算成本)

---

## Feature 4: 成本追踪

### Task 1: LLM Token 计数 + 成本记录

**Objective:** 每次 LLM 调用记录 token 用量和费用，写入 CostRecord。

**Files:**
- Modify: `llm.py` — call() 返回值改为包含 token 信息
- Create: `tests/test_cost.py`

**Step 1: Write failing test**
```python
# tests/test_cost.py
"""Tests for LLM cost tracking."""
from llm import CostRecord


def test_cost_record():
    """CostRecord should track tokens and cost."""
    cr = CostRecord(step="rewrite", input_tokens=500, output_tokens=2000, model="deepseek-chat")
    assert cr.step == "rewrite"
    assert cr.input_tokens == 500
    assert cr.output_tokens == 2000
    assert cr.total_tokens == 2500
    assert cr.cost_usd >= 0  # cost calculated from pricing


def test_cost_record_from_usage():
    """Should create CostRecord from OpenAI usage dict."""
    usage = {"prompt_tokens": 300, "completion_tokens": 1500}
    cr = CostRecord.from_usage(step="seo", usage=usage, model="deepseek-chat")
    assert cr.input_tokens == 300
    assert cr.output_tokens == 1500
    assert cr.total_tokens == 1800
```

**Step 2: Implement CostRecord in llm.py**
```python
from dataclasses import dataclass

# Pricing per 1M tokens (USD)
PRICING = {
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "qwen2.5:7b": {"input": 0.0, "output": 0.0},  # local, free
}

@dataclass
class CostRecord:
    step: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @classmethod
    def from_usage(cls, step: str, usage: dict, model: str = "") -> "CostRecord":
        inp = usage.get("prompt_tokens", 0)
        out = usage.get("completion_tokens", 0)
        pricing = PRICING.get(model, {"input": 0, "output": 0})
        cost = (inp * pricing["input"] + out * pricing["output"]) / 1_000_000
        return cls(step=step, input_tokens=inp, output_tokens=out, model=model, cost_usd=round(cost, 6))
```

**Step 3: Update LLM.call() to return CostRecord**
修改 `llm.py` 的 `call()` 方法，让它把 usage 信息存到 `self.last_cost`：
```python
# In LLM class:
self.last_cost: CostRecord | None = None

# In _call_with_fallback, after getting resp:
usage = resp.usage
if usage:
    self.last_cost = CostRecord.from_usage(
        step=cache_step or "unknown",
        usage={"prompt_tokens": usage.prompt_tokens, "completion_tokens": usage.completion_tokens},
        model=model,
    )
```

**Step 4: Commit**
```bash
git add llm.py tests/test_cost.py
git commit -m "feat: LLM cost tracking with token counting"
```

**Acceptance Criteria:**
1. CostRecord 含 step/input_tokens/output_tokens/model/cost_usd
2. from_usage() 从 OpenAI usage dict 创建
3. PRICING dict 可扩展
4. LLM.last_cost 在每次 call 后更新
5. 测试通过

---

### Task 2: Knowledge 成本日志 + Dashboard 成本面板

**Objective:** 每篇文章的 LLM 成本记录到 Knowledge，Dashboard 显示成本统计。

**Files:**
- Modify: `knowledge.py` — 添加 CostLog 模型和方法
- Modify: `reducer.py` — 每步后收集 CostRecord
- Modify: `web/api.py` — 添加 GET /api/costs
- Modify: `web/templates/dashboard.html` — 添加成本面板

**Step 1: Add to knowledge.py**
```python
class ArticleCost(BaseModel):
    url: str = ""
    keyword: str = ""
    total_cost_usd: float = 0.0
    steps: list[dict] = Field(default_factory=list)  # [{step, tokens, cost}]
    timestamp: str = ""

# In Knowledge class:
article_costs: list[ArticleCost] = Field(default_factory=list)

def record_article_cost(self, url: str, keyword: str, cost_records: list):
    """Record total cost for an article."""
    total = sum(c.cost_usd for c in cost_records)
    steps = [{"step": c.step, "tokens": c.total_tokens, "cost": c.cost_usd} for c in cost_records]
    self.article_costs.append(ArticleCost(
        url=url, keyword=keyword, total_cost_usd=total,
        steps=steps, timestamp=datetime.now().isoformat(),
    ))

def total_cost(self) -> float:
    return sum(a.total_cost_usd for a in self.article_costs)

def avg_cost(self) -> float:
    if not self.article_costs:
        return 0.0
    return self.total_cost() / len(self.article_costs)
```

**Step 2: Update reducer.py to collect costs**
在 reducer 中，每次调用 llm.call() 后收集 llm.last_cost。在 PASSED 分支调用 knowledge.record_article_cost()。

**Step 3: Add /api/costs endpoint**
返回 HTML：总费用、平均费用/文章、每篇文章的费用明细。

**Step 4: Commit**

---

## Feature 5: 人工审核队列

### Task 3: Review 状态 + 审核 API

**Objective:** verify 通过后状态改为 REVIEW，需要人工通过才变为 PASSED。

**Files:**
- Modify: `state.py` — 添加 REVIEW step
- Modify: `reducer.py` — PASSED 改为 REVIEW
- Modify: `web/api.py` — 添加审核 API
- Modify: `web/templates/dashboard.html` — 添加审核面板

**Step 1: Add REVIEW to Step enum**
```python
# state.py
class Step(str, Enum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    REWRITTEN = "rewritten"
    SEO_DONE = "seo_done"
    RENDERED = "rendered"
    VERIFIED = "verified"
    REVIEW = "review"      # NEW: waiting for human review
    PASSED = "passed"
    FAILED = "failed"
```

**Step 2: Update reducer.py**
在 verify passed 后，将 step 设为 REVIEW 而不是 PASSED：
```python
if state.verify and state.verify.passed:
    state.step = Step.REVIEW  # NOT PASSED — needs human review
    # ... record knowledge ...
    return state
```

**Step 3: Add review API endpoints**
```python
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
                continue
    # Return HTML cards for each pending article
    ...

@router.post("/review/{job_id}/approve")
async def approve_article(job_id: str):
    """Approve an article — change step from REVIEW to PASSED."""
    state_path = DATA_DIR / "states" / f"{job_id}.json"
    if not state_path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    data = json.loads(state_path.read_text())
    data["step"] = "passed"
    state_path.write_text(json.dumps(data, indent=2))
    return HTMLResponse('<span class="text-green-400">✅ Approved</span>')

@router.post("/review/{job_id}/reject")
async def reject_article(job_id: str):
    """Reject an article — change step from REVIEW to FAILED."""
    state_path = DATA_DIR / "states" / f"{job_id}.json"
    if not state_path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    data = json.loads(state_path.read_text())
    data["step"] = "failed"
    data["error"] = "Rejected by human reviewer"
    state_path.write_text(json.dumps(data, indent=2))
    return HTMLResponse('<span class="text-red-400">❌ Rejected</span>')
```

**Step 4: Add review panel to dashboard**
```html
<!-- Review Queue -->
<div class="bg-gray-900 rounded-lg p-6 mb-8">
    <h2 class="text-xl font-semibold mb-4">👁️ Review Queue</h2>
    <div hx-get="/api/review" hx-trigger="load, every 5s" hx-swap="innerHTML" id="review-queue">
        <p class="text-gray-500">Loading...</p>
    </div>
</div>
```

每个待审核文章显示：keyword、score、预览链接、Approve/Reject 按钮。

**Step 5: Commit**

---

## Feature 6: 质量趋势

### Task 4: 质量趋势 API + Dashboard 图表

**Objective:** 用纯 CSS/SVG 画 verify score 趋势图。

**Files:**
- Modify: `web/api.py` — 添加 GET /api/trends
- Modify: `web/templates/dashboard.html` — 添加趋势面板

**Step 1: Add /api/trends endpoint**
从 states/ 目录读取所有 PASSED/REVIEW 的文章，按时间排序，返回 SVG 折线图。

```python
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
```

**Step 2: Add trend panel to dashboard**
```html
<!-- Quality Trends -->
<div class="bg-gray-900 rounded-lg p-6 mb-8">
    <h2 class="text-xl font-semibold mb-4">📈 Quality Trends</h2>
    <div hx-get="/api/trends" hx-trigger="load" hx-swap="innerHTML" id="trends-chart">
        <p class="text-gray-500">Loading...</p>
    </div>
</div>
```

**Step 3: Commit**

---

## Feature 7: 静态站发布

### Task 5: 静态站生成器

**Objective:** 从 output/ 目录生成一个可部署的静态站点（index.html + 文章页 + RSS）。

**Files:**
- Create: `publisher.py` — 静态站生成器
- Modify: `cli.py` — 添加 publish 子命令
- Create: `tests/test_publisher.py`

**Step 1: Write failing test**
```python
# tests/test_publisher.py
"""Tests for static site publisher."""
import tempfile
from pathlib import Path
from publisher import generate_site


def test_generate_site(tmp_path):
    """Should generate index.html + copy articles."""
    # Setup: create mock output articles
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "test-article.html").write_text("<html><body><h1>Test</h1></body></html>")
    (output_dir / "another-post.html").write_text("<html><body><h1>Another</h1></body></html>")

    site_dir = tmp_path / "site"
    generate_site(output_dir=output_dir, site_dir=site_dir, title="My Content Hub")

    assert (site_dir / "index.html").exists()
    assert (site_dir / "test-article.html").exists()
    assert (site_dir / "another-post.html").exists()
    index = (site_dir / "index.html").read_text()
    assert "My Content Hub" in index
    assert "test-article.html" in index


def test_generate_rss(tmp_path):
    """Should generate RSS feed."""
    from publisher import generate_rss

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "post.html").write_text("<html><body><h1>Post</h1></body></html>")

    site_dir = tmp_path / "site"
    site_dir.mkdir()
    generate_rss(output_dir=output_dir, site_dir=site_dir, title="Feed", base_url="https://example.com")

    rss_path = site_dir / "feed.xml"
    assert rss_path.exists()
    content = rss_path.read_text()
    assert "<rss" in content
    assert "Post" in content
```

**Step 2: Implement publisher.py**
```python
"""Static site publisher — generate index + RSS from output/ articles."""
import re
from datetime import datetime
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring


def generate_site(output_dir: Path, site_dir: Path, title: str = "AI Content Hub"):
    """Generate a static site from HTML articles."""
    site_dir.mkdir(parents=True, exist_ok=True)

    articles = []
    for html_file in sorted(output_dir.glob("*.html")):
        # Extract title from HTML
        content = html_file.read_text(encoding="utf-8")
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", content, re.IGNORECASE | re.DOTALL)
        article_title = h1.group(1).strip() if h1 else html_file.stem.replace("-", " ").title()

        # Copy article
        dest = site_dir / html_file.name
        dest.write_text(content, encoding="utf-8")

        articles.append({"file": html_file.name, "title": article_title})

    # Generate index.html
    index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    <link rel="alternate" type="application/rss+xml" title="RSS" href="/feed.xml">
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-950 text-gray-100 min-h-screen">
    <div class="max-w-4xl mx-auto p-6">
        <h1 class="text-3xl font-bold mb-8">{title}</h1>
        <div class="space-y-4">
"""
    for a in articles:
        index_html += f'            <a href="{a["file"]}" class="block bg-gray-900 hover:bg-gray-800 rounded-lg p-4 transition-colors">\n'
        index_html += f'                <h2 class="text-xl font-semibold text-blue-400">{a["title"]}</h2>\n'
        index_html += f'            </a>\n'

    index_html += """        </div>
        <footer class="mt-12 text-gray-500 text-sm">
            <a href="/feed.xml" class="hover:text-gray-300">RSS Feed</a>
        </footer>
    </div>
</body>
</html>"""

    (site_dir / "index.html").write_text(index_html, encoding="utf-8")
    generate_rss(output_dir, site_dir, title)


def generate_rss(output_dir: Path, site_dir: Path, title: str = "AI Content Hub",
                 base_url: str = "https://example.com"):
    """Generate RSS 2.0 feed."""
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = title
    SubElement(channel, "link").text = base_url
    SubElement(channel, "description").text = f"{title} — AI-generated content"
    SubElement(channel, "lastBuildDate").text = datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")

    for html_file in sorted(output_dir.glob("*.html"), reverse=True)[:20]:
        content = html_file.read_text(encoding="utf-8")
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", content, re.IGNORECASE | re.DOTALL)
        article_title = h1.group(1).strip() if h1 else html_file.stem

        item = SubElement(channel, "item")
        SubElement(item, "title").text = article_title
        SubElement(item, "link").text = f"{base_url}/{html_file.name}"
        SubElement(item, "guid").text = f"{base_url}/{html_file.name}"

    rss_xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(rss, encoding="unicode")
    (site_dir / "feed.xml").write_text(rss_xml, encoding="utf-8")
```

**Step 3: Add CLI command**
```python
p_publish = sub.add_parser("publish", help="Generate static site from articles")
p_publish.add_argument("--output", default="output", help="Articles directory")
p_publish.add_argument("--site-dir", default="site", help="Output site directory")
p_publish.add_argument("--title", default="AI Content Hub")

# Handler:
elif args.command == "publish":
    from publisher import generate_site
    generate_site(Path(args.output), Path(args.site_dir), args.title)
    print(f"Site generated: {args.site_dir}/")
    print(f"  index.html + {len(list(Path(args.site_dir).glob('*.html')))} articles + feed.xml")
```

**Step 4: Commit**

---

### Task 6: Dashboard 发布按钮 + 最终集成

**Objective:** Dashboard 加发布按钮，所有面板整合。

**Files:**
- Modify: `web/api.py` — POST /api/publish
- Modify: `web/templates/dashboard.html` — 发布按钮 + 整合所有面板

**Step 1: Add publish endpoint**
```python
@router.post("/publish")
async def publish_site():
    """Generate static site from published articles."""
    from publisher import generate_site
    site_dir = DATA_DIR / "site"
    generate_site(DATA_DIR / "output", site_dir, title="AI Content Hub")
    count = len(list(site_dir.glob("*.html"))) - 1  # exclude index
    return HTMLResponse(f'<span class="text-green-400">✅ Site generated: {count} articles + index + RSS</span>')
```

**Step 2: Update dashboard layout**

完整 Dashboard 布局：
```
┌─────────────────────────────────────────────────┐
│ 🕷️ AI Crawler v2                                │
├────────┬────────┬────────┬────────┬─────────────┤
│ URLs   │ Queue  │ Score  │ Cost   │ Coverage    │
│ (蓝)   │ (紫)   │ (黄)   │ (红)   │ (绿)        │
├────────┴────────┴────────┴────────┴─────────────┤
│ New Crawl Job [URL] [Keyword] [Source] [🚀]     │
│ Batch Import [CSV file] [📤 Import]             │
├─────────────────────────────────────────────────┤
│ 👁️ Review Queue                                 │
│ [article cards with Approve/Reject buttons]     │
├─────────────────────────────────────────────────┤
│ Recent Jobs (auto-refresh)                      │
├─────────────────────────────────────────────────┤
│ 📈 Quality Trends (SVG chart)                   │
├─────────────────────────────────────────────────┤
│ 📚 Generated Articles  [Publish Site 🌐]        │
├─────────────────────────────────────────────────┤
│ 🧠 Knowledge Panel                              │
│ 🎯 Keyword Coverage                             │
│ 💰 Cost Breakdown                               │
└─────────────────────────────────────────────────┘
```

**Step 3: Commit**

---

## Execution Order

```
Task 1 (CostRecord + LLM) → Task 2 (Knowledge cost log + API)
  ↓
Task 3 (Review state + API)
  ↓
Task 4 (Quality trends SVG)
  ↓
Task 5 (Static site publisher)
  ↓
Task 6 (Dashboard integration)
```
