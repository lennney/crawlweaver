# YouTube-to-Article 初始项目搭建

> **For Hermes:** 按计划逐任务执行。**提取已有代码的任务**先验证（确认已有代码正确）→ 写测试 → 移植实现。**新增逻辑的任务**严格 TDD：先写测试（RED）→ 写实现（GREEN）→ 验证。完成后 subagent 审查。

**目标：** 搭建 youtube-to-article 独立项目，从 ai-crawler 抽取核心引擎，合并 diyhub 的 YouTube→文章工作流，做成纯 AI 调用的 CLI/Python API 工具。

**平台：** macOS（ai 调用用）
**驱动：** yt-dlp（YDT）
**架构：** ai-crawler 的 component-based 管线引擎
**LLM：** 任意 OpenAI 兼容 API（DeepSeek / OpenAI / Anthropic 等），通过环境变量配置

---

## 技术栈

| 技术 | 选型理由 |
|------|---------|
| Python 3.12+ | macOS 自带，AI agent 标配 |
| uv | 包管理，快，PEP 668 友好 |
| Pydantic v2 | 数据契约（从 ai-crawler 沿用） |
| yt-dlp | 视频/字幕/元数据获取 |
| ffmpeg | 关键帧截图 |
| Jinja2 | HTML 模板渲染 |
| deepseek / openai SDK | LLM 改写 + SEO |
| click | CLI（AI agent 调用友好） |

**不做的：**
- ❌ Web 界面（FastAPI / Next.js）
- ❌ 数据库持久化（SQLite / Catalog）
- ❌ AI 质检/自检（ai_verify 先不加）
- ❌ 批量调度（batch 先不加）
- ❌ Playwright / stealth browser（Level 1 反爬足够）

---

## 目录结构

```
youtube-to-article/
├── pyproject.toml              # 包定义 + 依赖
├── .env.example                # 环境变量模板
├── .gitignore
├── README.md
│
├── src/
│   └── ytarticle/
│       ├── __init__.py         # 版本号 + 公开 API
│       ├── cli.py              # AI 调用的 CLI（click）
│       │
│       ├── core/               # 管线引擎（从 ai-crawler engine/ 抽）
│       │   ├── __init__.py
│       │   ├── schema.py       # ContentItem（简化为 article-only 版）
│       │   ├── base.py         # BaseComponent 基类
│       │   ├── registry.py     # 组件自动发现
│       │   └── pipeline.py     # Pipeline 编排器（轻量版）
│       │
├── support/            # 反爬 + 工具层
│   ├── __init__.py
│   ├── cookies.py      # CookieManager（加载/刷新/多账号）
│   ├── proxy.py        # ProxyManager（静态/轮换）
│   └── llm.py          # LLMClient（从 ai-crawler 抽，去缓存）
│       │
│       ├── components/         # 步骤组件
│       │   ├── __init__.py
│       │   ├── _template.py    # 新组件模板
│       │   ├── sources/
│       │   │   ├── __init__.py
│       │   │   ├── youtube_extract.py   # yt-dlp 字幕提取
│       │   │   └── youtube_frames.py    # 视频下载 + ffmpeg 帧提取
│       │   ├── processors/
│       │   │   ├── __init__.py
│       │   │   ├── ai_rewrite.py        # LLM 改写
│       │   │   ├── seo_metadata.py      # SEO 元数据
│       │   │   └── html_render.py       # HTML 渲染（可换模板）
│       │   └── checkers/
│       │       ├── __init__.py
│       │       └── content_check.py     # 基础质量检查
│       │
│       └── templates/          # 模板目录（可插拔）
│           ├── __init__.py
│           ├── base.py         # TemplateLoader 接口
│           ├── diyhub/         # MakeDIYHub 风格
│           │   └── article.html
│           └── default/        # 默认通用风格
│               └── article.html
│
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_schema.py
    ├── test_pipeline.py
    ├── test_components.py
    └── test_cli.py
```

---

## 任务拆分

### Task 1: 项目脚手架

**Objective:** 建项目目录结构、pyproject.toml、依赖管理、gitignore

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `README.md`
- Create: `src/ytarticle/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Step 1: Write pyproject.toml**

```toml
[project]
name = "youtube-to-article"
version = "0.1.0"
description = "YouTube video → DIY article pipeline. yt-dlp + AI rewrite + SEO + HTML."
authors = [{ name = "lennney" }]
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.0",
    "click>=8.0",
    "jinja2>=3.0",
    "markdown>=3.0",
    "openai>=1.0",
    "python-dotenv>=1.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
]

[project.scripts]
ytarticle = "ytarticle.cli:cli"

[tool.pytest.ini_options]
testpaths = ["tests"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/ytarticle"]
```

**Step 2: Write .gitignore**

```gitignore
# Secrets
.env
*.txt
!requirements*.txt

# Python
__pycache__/
*.pyc
*.pyo
.venv/
venv/

# Output
output/
cache/

# IDE
.idea/
.vscode/
*.swp

# macOS
.DS_Store
```

**Step 3: Write .env.example**

```
# LLM — OpenAI 兼容 API（任意供应商）
# 支持：DeepSeek / OpenAI / Anthropic（via proxy）/ 任何 OpenAI 兼容服务
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat

# YouTube cookies path
COOKIES_PATH=cookies.txt

# Proxy (optional, leave blank to disable)
HTTP_PROXY=
HTTPS_PROXY=
```

**Step 4: Write __init__.py**

```python
__version__ = "0.1.0"
```

**Step 5: Verify**

```bash
cd ~/youtube-to-article
uv sync
uv run python -c "import ytarticle; print(ytarticle.__version__)"
# Expected: 0.1.0
```

**Acceptance Criteria:**
1. `uv sync` installs all dependencies without error
2. `uv run python -c "import ytarticle"` succeeds
3. `.gitignore` excludes `.env`, `__pycache__/`, `output/`
4. `.env.example` documents all required env vars

---

### Task 2: Core Schema (ContentItem)

**Objective:** 从 ai-crawler 抽取 ContentItem + ImageInfo + ArtifactPaths，简化为 article-only 版

**Files:**
- Create: `src/ytarticle/core/__init__.py`
- Create: `src/ytarticle/core/schema.py`
- Create: `tests/test_schema.py`

**Step 1: Write schema.py**

```python
"""Unified data contract — single schema all components share."""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class Source(str, Enum):
    YOUTUBE = "youtube"
    CUSTOM = "custom"


class ImageInfo(BaseModel):
    path: str = ""
    alt: str = ""
    source_url: str = ""
    step: int = 0


class ArtifactPaths(BaseModel):
    raw_text: str = ""
    article_md: str = ""
    html_path: str = ""
    images_dir: str = ""
    timed_transcript: str = ""
    cover_img: str = ""


class SeoMetadata(BaseModel):
    title_tag: str = ""
    meta_description: str = ""
    url_slug: str = ""
    h1: str = ""


class ContentItem(BaseModel):
    """Unified data contract.

    All components read/write this. Fields grouped by pipeline stage.
    """

    # --- Source ---
    source: Source = Source.YOUTUBE
    source_id: str = ""
    source_url: str = ""
    source_metadata: dict[str, Any] = Field(default_factory=dict)

    # --- Raw ---
    title: str = ""
    raw_text: str = ""
    images: list[ImageInfo] = Field(default_factory=list)

    # --- Classification ---
    category: str = ""
    keyword: str = ""
    tags: list[str] = Field(default_factory=list)
    target_words: int = 1500
    author: str = ""

    # --- Article ---
    article_md: str = ""
    difficulty: str = ""          # easy | medium | hard
    estimated_time: str = ""
    estimated_cost: str = ""
    materials: list[str] = Field(default_factory=list)

    # --- SEO ---
    seo: SeoMetadata = Field(default_factory=SeoMetadata)

    # --- Artifacts ---
    artifacts: ArtifactPaths = Field(default_factory=ArtifactPaths)

    # --- Pipeline state ---
    status: str = "pending"       # pending | running | done | skipped | failed
    error: str = ""
    started_at: str = ""
    completed_at: str = ""

    def mark_running(self):
        self.status = "running"
        if not self.started_at:
            self.started_at = datetime.now().isoformat()

    def mark_done(self):
        self.status = "done"
        self.completed_at = datetime.now().isoformat()

    def mark_failed(self, error: str):
        self.status = "failed"
        self.error = error
        self.completed_at = datetime.now().isoformat()

    def task_id(self) -> str:
        return f"{self.source.value}_{self.source_id}"


def make_item(source: str, source_id: str, **kw) -> ContentItem:
    return ContentItem(source=Source(source), source_id=source_id, **kw)
```

**Step 2: Write test_schema.py**

```python
"""Tests for schema module."""
import pytest
from ytarticle.core.schema import ContentItem, Source, make_item


class TestContentItem:
    def test_default_creation(self):
        item = ContentItem()
        assert item.status == "pending"
        assert item.source == Source.YOUTUBE

    def test_make_item_with_source_id(self):
        item = make_item("youtube", "abc123", title="Test Video")
        assert item.source_id == "abc123"
        assert item.title == "Test Video"
        assert item.task_id() == "youtube_abc123"

    def test_mark_running_sets_timestamp(self):
        item = ContentItem()
        item.mark_running()
        assert item.status == "running"
        assert item.started_at != ""

    def test_mark_done(self):
        item = ContentItem()
        item.mark_done()
        assert item.status == "done"
        assert item.completed_at != ""

    def test_mark_failed(self):
        item = ContentItem()
        item.mark_failed("Something broke")
        assert item.status == "failed"
        assert "Something broke" in item.error

    def test_image_info_defaults(self):
        from ytarticle.core.schema import ImageInfo
        img = ImageInfo()
        assert img.path == ""
        assert img.step == 0
```

**Step 3: Verify**

```bash
uv run pytest tests/test_schema.py -v
# Expected: 6 passed
```

**Acceptance Criteria:**
1. `ContentItem` creates with sensible defaults
2. `make_item()` is a clean factory
3. Status methods (`mark_running`, `mark_done`, `mark_failed`) work correctly
4. `task_id()` returns `{source}_{source_id}`
5. All 6 tests pass

---

### Task 3: BaseComponent + Registry

**Objective:** 从 ai-crawler 抽取 BaseComponent 和 Registry，简化

**Files:**
- Create: `src/ytarticle/core/base.py`
- Create: `src/ytarticle/core/registry.py`
- Create: `tests/test_base.py`

**Step 1: Write base.py**

```python
"""Component base class — every component must implement this."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

from ytarticle.core.schema import ContentItem


class ComponentError(Exception):
    """Raised when a component encounters a non-recoverable error."""


class BaseComponent(ABC):
    """Base class for pipeline components.

    Subclass and implement:
        name: str
        version: str
        run(item, config) -> ContentItem
    """

    name: str = "unnamed"
    version: str = "1.0.0"
    required_fields: list[str] = []
    output_fields: list[str] = []

    @abstractmethod
    def run(self, item: ContentItem, config: dict[str, Any]) -> ContentItem:
        ...

    def validate_input(self, item: ContentItem) -> list[str]:
        """Return list of missing required fields."""
        return [f for f in self.required_fields
                if not getattr(item, f, None)]

    def validate_output(self, item: ContentItem) -> list[str]:
        """Return list of missing output fields."""
        return [f for f in self.output_fields
                if not getattr(item, f, None)]
```

**Step 2: Write registry.py**

```python
"""Component registry — auto-discover and manage components."""
from __future__ import annotations
import importlib
from pathlib import Path
from typing import Any

from ytarticle.core.base import BaseComponent


class Registry:
    """Component registry with auto-discovery."""

    def __init__(self):
        self._components: dict[str, BaseComponent] = {}
        self._components_dir = Path(__file__).resolve().parent.parent / "components"

    def register(self, component: BaseComponent) -> None:
        self._components[component.name] = component

    def get(self, name: str) -> BaseComponent:
        if name not in self._components:
            raise KeyError(
                f"Component '{name}' not found. "
                f"Available: {list(self._components.keys())}"
            )
        return self._components[name]

    def has(self, name: str) -> bool:
        return name in self._components

    def list_all(self) -> list[str]:
        return list(self._components.keys())

    def discover(self) -> int:
        """Auto-scan component subdirectories and register."""
        subdirs = ["sources", "processors", "checkers"]
        count = 0
        for subdir in subdirs:
            pkg_dir = self._components_dir / subdir
            if not pkg_dir.is_dir():
                continue
            for py_file in sorted(pkg_dir.glob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                module_name = f"ytarticle.components.{subdir}.{py_file.stem}"
                try:
                    mod = importlib.import_module(module_name)
                    if hasattr(mod, "create"):
                        comp = mod.create()
                        if isinstance(comp, BaseComponent):
                            self.register(comp)
                            count += 1
                except Exception as e:
                    print(f"[registry] Warn: failed to load {module_name}: {e}")
        return count
```

**Step 3: Write test_base.py**

```python
"""Tests for base component and registry."""
import pytest
from ytarticle.core.base import BaseComponent, ComponentError
from ytarticle.core.registry import Registry
from ytarticle.core.schema import ContentItem, make_item


class DummyComponent(BaseComponent):
    name = "dummy"
    version = "1.0.0"
    required_fields = ["title"]
    output_fields = ["article_md"]

    def run(self, item: ContentItem, config: dict) -> ContentItem:
        item.article_md = f"# {item.title}"
        return item


class TestBaseComponent:
    def test_validate_input_missing(self):
        comp = DummyComponent()
        item = ContentItem()
        missing = comp.validate_input(item)
        assert "title" in missing

    def test_validate_input_ok(self):
        comp = DummyComponent()
        item = make_item("youtube", "123", title="Hello")
        missing = comp.validate_input(item)
        assert missing == []

    def test_run(self):
        comp = DummyComponent()
        item = make_item("youtube", "123", title="Test")
        result = comp.run(item, {})
        assert result.article_md == "# Test"


class TestRegistry:
    def test_register_and_get(self):
        reg = Registry()
        comp = DummyComponent()
        reg.register(comp)
        assert reg.has("dummy")
        assert reg.get("dummy") is comp

    def test_list_all(self):
        reg = Registry()
        reg.register(DummyComponent())
        assert "dummy" in reg.list_all()

    def test_get_missing_raises(self):
        reg = Registry()
        with pytest.raises(KeyError):
            reg.get("nonexistent")
```

**Step 4: Verify**

```bash
uv run pytest tests/test_base.py -v
# Expected: 7 passed
uv run pytest tests/test_schema.py tests/test_base.py -v
# Expected: 13 passed
```

**Acceptance Criteria:**
1. `BaseComponent` enforces `run()` via ABC
2. `validate_input` / `validate_output` check against field lists
3. `Registry.discover()` auto-imports `.py` files with `create()`
4. Missing component raises `KeyError` with available list
5. All 7 tests pass

---

### Task 4: Pipeline Engine

**Objective:** 轻量 Pipeline 编排器，配置驱动，从 ai-crawler engine/workflow.py 简化

**Files:**
- Create: `src/ytarticle/core/pipeline.py`
- Create: `tests/test_pipeline.py`

**Step 1: Write pipeline.py**

```python
"""Pipeline engine — config-driven step orchestrator.

Simplified from ai-crawler's workflow.py:
- No gates (ai_verify not included yet)
- No catalog/SQLite persistence
- No event store
- No evaluator-optimizer loop
"""
from __future__ import annotations
import logging
import time
from pathlib import Path
from typing import Any, Optional

import yaml

from ytarticle.core.schema import ContentItem
from ytarticle.core.base import ComponentError
from ytarticle.core.registry import Registry

logger = logging.getLogger("ytarticle.pipeline")


class Pipeline:
    """Config-driven content pipeline."""

    def __init__(self, config: dict[str, Any] | str | Path):
        if isinstance(config, (str, Path)):
            config = self._load_config(config)
        self.config = config
        self.steps = config.get("steps", [])
        self.max_retries = config.get("max_retries", 2)
        self.registry = Registry()
        self.registry.discover()

    @staticmethod
    def _load_config(path: str | Path) -> dict:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def run(self, item: ContentItem) -> ContentItem:
        """Run all configured steps."""
        item.mark_running()
        task_id = item.task_id()

        for step_idx, step_conf in enumerate(self.steps):
            comp_name = step_conf.get("component", "")
            comp_config = step_conf.get("config", {})
            step_name = step_conf.get("id", comp_name)

            if not self.registry.has(comp_name):
                item.mark_failed(f"Component '{comp_name}' not found")
                return item

            comp = self.registry.get(comp_name)

            # Validate input
            missing = comp.validate_input(item)
            if missing:
                item.mark_failed(f"{comp_name}: missing {missing}")
                return item

            # Execute with retry
            success = False
            last_error = ""
            for attempt in range(self.max_retries + 1):
                try:
                    logger.info(f"[pipeline] Running: {comp_name}"
                                + (f" (attempt {attempt+1})" if attempt > 0 else ""))
                    item = comp.run(item, comp_config)
                    success = True
                    break
                except ComponentError as e:
                    last_error = str(e)
                    if attempt < self.max_retries:
                        time.sleep(2 ** attempt)
                except Exception as e:
                    last_error = f"{type(e).__name__}: {e}"
                    logger.warning(f"[pipeline] {comp_name} error: {e}")
                    if attempt < self.max_retries:
                        time.sleep(2 ** attempt)

            if not success:
                item.mark_failed(f"{comp_name}: {last_error}")
                return item

            logger.info(f"[pipeline] {comp_name} done")

        item.mark_done()
        logger.info(f"[pipeline] Done: {task_id}")
        return item


def run_from_config(config_path: str, item: ContentItem) -> ContentItem:
    """Convenience: one-liner to run a pipeline."""
    pipe = Pipeline(config_path)
    return pipe.run(item)
```

**Step 1: Write conftest.py with shared components**

```python
"""Shared test fixtures and helpers."""
import pytest
from ytarticle.core.base import BaseComponent
from ytarticle.core.schema import ContentItem


class DummyComponent(BaseComponent):
    """A no-op component for pipeline testing."""
    name = "dummy"
    version = "1.0.0"
    required_fields = ["title"]
    output_fields = ["article_md"]

    def run(self, item: ContentItem, config: dict) -> ContentItem:
        item.article_md = f"# {item.title}"
        return item


@pytest.fixture
def dummy_comp():
    return DummyComponent()
```

**Step 2: Write test_pipeline.py**

```python
"""Tests for pipeline engine."""
import tempfile
from pathlib import Path
import yaml

import pytest
from ytarticle.core.pipeline import Pipeline
from ytarticle.core.schema import ContentItem, make_item
from ytarticle.core.base import BaseComponent


class UppercaseTitle(BaseComponent):
    name = "uppercase_title"
    version = "1.0.0"
    required_fields = ["title"]

    def run(self, item, config):
        item.article_md = item.title.upper()
        return item


class TestPipeline:
    def test_pipeline_with_components(self, dummy_comp):
        pipe = Pipeline({"steps": [{"component": "dummy"}]})
        pipe.registry.register(dummy_comp)

        item = make_item("youtube", "123", title="Hello")
        result = pipe.run(item)
        assert result.status == "done"
        assert result.article_md == "# Hello"

    def test_pipeline_component_not_found(self):
        pipe = Pipeline({"steps": [{"component": "nonexistent"}]})
        item = make_item("youtube", "123")
        result = pipe.run(item)
        assert result.status == "failed"
        assert "not found" in result.error

    def test_pipeline_missing_input(self, dummy_comp):
        pipe = Pipeline({"steps": [{"component": "dummy"}]})
        pipe.registry.register(dummy_comp)

        item = ContentItem()  # No title
        result = pipe.run(item)
        assert result.status == "failed"
        assert "missing" in result.error

    def test_pipeline_yaml_config(self):
        config_yaml = """
steps:
  - component: uppercase_title
    id: step1
"""
        config = yaml.safe_load(config_yaml)
        pipe = Pipeline(config)
        pipe.registry.register(UppercaseTitle())
        item = make_item("youtube", "123", title="hello")
        result = pipe.run(item)
        assert result.status == "done"
        assert result.article_md == "HELLO"
```

**Step 3: Verify**

```bash
uv run pytest tests/test_pipeline.py -v
# Expected: 4 passed
uv run pytest tests/ -v
# Expected: 17 passed
```

**Acceptance Criteria:**
1. Pipeline runs configured steps in order
2. Component not found → item marked failed
3. Missing input → item marked failed
4. YAML config loading works
5. All 4 pipeline tests pass, no regressions in previous tests

---

### Task 5: Support Layer — CookieManager + ProxyManager + LLMClient

**Objective:** 轻量反爬工具层，供组件调用

**Files:**
- Create: `src/ytarticle/support/__init__.py`
- Create: `src/ytarticle/support/cookies.py`
- Create: `src/ytarticle/support/proxy.py`
- Create: `src/ytarticle/support/llm.py`
- Create: `tests/test_support.py`

**Step 1: Write cookies.py**

```python
"""Cookie management for yt-dlp and HTTP requests."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional


class CookieManager:
    """Manage YouTube cookies for yt-dlp authentication.

    Cookies are plain Netscape-format files (same as browser export).
    """

    def __init__(self, cookie_path: Optional[str] = None):
        self._path: Optional[Path] = None
        if cookie_path:
            self._path = Path(cookie_path)
        elif "COOKIES_PATH" in os.environ:
            self._path = Path(os.environ["COOKIES_PATH"])
        self._validated = False

    @property
    def path(self) -> Optional[str]:
        return str(self._path) if self._path else None

    @property
    def exists(self) -> bool:
        return self._path is not None and self._path.exists()

    @property
    def is_valid(self) -> bool:
        """Quick check: has non-empty cookie lines."""
        if not self.exists:
            return False
        try:
            content = self._path.read_text(encoding="utf-8")
            # Netscape cookies have lines with 6+ tab-separated fields
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    parts = line.split("\t")
                    if len(parts) >= 6:
                        return True
            return False
        except OSError:
            return False

    def yt_dlp_args(self) -> list[str]:
        """Return yt-dlp CLI args for cookies."""
        if self.exists:
            return ["--cookies", str(self._path)]
        return []
```

**Step 2: Write proxy.py**

```python
"""Proxy management for HTTP requests and yt-dlp."""
from __future__ import annotations
import os
from typing import Optional


class ProxyManager:
    """Manage proxy configuration.

    Reads from HTTP_PROXY/HTTPS_PROXY env vars or explicit config.
    """

    def __init__(self, http: Optional[str] = None, https: Optional[str] = None,
                 rotate: bool = False):
        self.http = http or os.environ.get("HTTP_PROXY", "")
        self.https = https or os.environ.get("HTTPS_PROXY", http or os.environ.get("HTTP_PROXY", ""))
        self._rotate = rotate
        if rotate:
            self._proxy_list = []
            if self.http:
                self._proxy_list.append(self.http)

    @property
    def enabled(self) -> bool:
        return bool(self.http) or bool(self.https)

    def yt_dlp_args(self) -> list[str]:
        """Return yt-dlp CLI args for proxy."""
        if self.http:
            return ["--proxy", self.http]
        return []

    def requests_kwargs(self) -> dict:
        """Return requests-compatible proxy dict."""
        if not self.enabled:
            return {}
        return {"http": self.http, "https": self.https}
```

**Step 3: Write llm.py（从 ai-crawler 简化，去掉缓存）**

```python
"""Unified LLM client — DeepSeek → Ollama fallback."""
from __future__ import annotations
import logging
import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("ytarticle.llm")

_CLIENTS: dict[str, object] = {}


def _get_client(api_key: str, base_url: str, timeout: int = 120):
    cache_key = f"{api_key[:8]}::{base_url}"
    if cache_key not in _CLIENTS:
        from openai import OpenAI
        _CLIENTS[cache_key] = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
    return _CLIENTS[cache_key]


def call_llm(system_prompt: str, user_prompt: str,
             max_tokens: int = 8192, temperature: float = 0.8) -> str:
    """Call any OpenAI-compatible API.

    Configure via .env or environment:
      LLM_API_KEY   — API key (required)
      LLM_BASE_URL  — API base URL (default: https://api.deepseek.com)
      LLM_MODEL     — Model name (default: deepseek-chat)

    Examples:
      DeepSeek:   LLM_BASE_URL=https://api.deepseek.com        LLM_MODEL=deepseek-chat
      OpenAI:     LLM_BASE_URL=https://api.openai.com/v1       LLM_MODEL=gpt-4o
      Anthropic:  LLM_BASE_URL=https://api.anthropic.com/v1    LLM_MODEL=claude-sonnet-4
      vLLM:       LLM_BASE_URL=http://localhost:8000/v1        LLM_MODEL=my-model
    """
    api_key = os.getenv("LLM_API_KEY", "")
    base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    model = os.getenv("LLM_MODEL", "deepseek-chat")

    if not api_key:
        raise RuntimeError(
            "LLM_API_KEY not set. Configure in .env:\n"
            "  LLM_API_KEY=sk-xxx\n"
            "  LLM_BASE_URL=https://api.deepseek.com\n"
            "  LLM_MODEL=deepseek-chat"
        )

    try:
        client = _get_client(api_key, base_url)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        raise RuntimeError(f"LLM call failed: {e}") from e
```

**Step 1: Write failing test**

```python
"""Tests for support layer."""
import tempfile
from pathlib import Path
import pytest
from ytarticle.support.cookies import CookieManager
from ytarticle.support.proxy import ProxyManager


class TestCookieManager:
    def test_no_path_returns_empty_args(self):
        mgr = CookieManager()
        assert mgr.yt_dlp_args() == []

    def test_with_valid_cookie_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write(".youtube.com\tTRUE\t/\tTRUE\t0\tTEST\tvalue\n")
            p = f.name
        mgr = CookieManager(p)
        assert mgr.exists
        assert mgr.is_valid
        assert "--cookies" in mgr.yt_dlp_args()
        Path(p).unlink()

    def test_is_valid_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("# just a comment\n")
            p = f.name
        mgr = CookieManager(p)
        assert mgr.exists
        assert not mgr.is_valid
        Path(p).unlink()


class TestProxyManager:
    def test_disabled_by_default(self):
        mgr = ProxyManager()
        assert not mgr.enabled
        assert mgr.yt_dlp_args() == []

    def test_with_http_proxy(self):
        mgr = ProxyManager(http="http://127.0.0.1:8080")
        assert mgr.enabled
        assert "--proxy" in mgr.yt_dlp_args()
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/test_support.py -v
# Expected: FAIL — imports not found (modules don't exist yet)
```

**Step 3: Write implementations**

(Write cookies.py, proxy.py, llm.py — same code as originally planned, with fixes:)

In cookies.py, remove unused `_validated`:

```python
class CookieManager:
    def __init__(self, cookie_path: Optional[str] = None):
        self._path: Optional[Path] = None
        if cookie_path:
            self._path = Path(cookie_path)
        elif "COOKIES_PATH" in os.environ:
            self._path = Path(os.environ["COOKIES_PATH"])

    @property
    def path(self) -> Optional[str]:
        return str(self._path) if self._path else None
    ...
```

In proxy.py, keep only `yt_dlp_args()` (remove unused `requests_kwargs`):

```python
class ProxyManager:
    def __init__(self, http: Optional[str] = None, https: Optional[str] = None):
        self.http = http or os.environ.get("HTTP_PROXY", "")
        self.https = https or os.environ.get("HTTPS_PROXY", http or "")

    @property
    def enabled(self) -> bool:
        return bool(self.http) or bool(self.https)

    def yt_dlp_args(self) -> list[str]:
        if self.http:
            return ["--proxy", self.http]
        return []
```

**Step 4: Verify**

```bash
uv run pytest tests/test_support.py -v
# Expected: 5 passed

**Step 5: Verify**

```bash
uv run pytest tests/test_support.py -v
# Expected: 6 passed
uv run pytest tests/ -v
# Expected: 23 passed
```

**Acceptance Criteria:**
1. `CookieManager` correctly loads Netscape cookies
2. `CookieManager.yt_dlp_args()` returns proper `--cookies` flags
3. `ProxyManager` reads from constructor args and env vars
4. `call_llm()` raises clear error when LLM_API_KEY is not set
5. All 5 tests pass

---

### Task 6: YouTube Components

**Objective:** 从 diyhub + ai-crawler 合并 YouTube 提取和帧提取组件

**Files:**
- Create: `src/ytarticle/components/__init__.py`
- Create: `src/ytarticle/components/_template.py`
- Create: `src/ytarticle/components/sources/__init__.py`
- Create: `src/ytarticle/components/sources/youtube_extract.py`
- Create: `src/ytarticle/components/sources/youtube_frames.py`
- Create: `tests/test_youtube_components.py`

**Step 1: Write _template.py（新组件模板）**

```python
"""Template for new components — copy this to create a component."""
from __future__ import annotations
from typing import Any
from ytarticle.core.base import BaseComponent, ComponentError
from ytarticle.core.schema import ContentItem


class TemplateComponent(BaseComponent):
    name = "template"
    version = "1.0.0"
    required_fields: list[str] = []
    output_fields: list[str] = []

    def run(self, item: ContentItem, config: dict[str, Any]) -> ContentItem:
        # Your logic here
        return item


def create():
    """Factory function — registry.discover() calls this."""
    return TemplateComponent()
```

**Step 2: Write youtube_extract.py（合并 diyhub + ai-crawler）**

```python
"""YouTube subtitle extraction via yt-dlp."""
from __future__ import annotations
import json
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from ytarticle.core.base import BaseComponent, ComponentError
from ytarticle.core.schema import ContentItem
from ytarticle.support.cookies import CookieManager
from ytarticle.support.proxy import ProxyManager

logger = logging.getLogger("ytarticle.youtube_extract")


def _sanitize_filename(s: str) -> str:
    return re.sub(r'[^\w\-_\. ]', '_', s)


class YouTubeExtract(BaseComponent):
    name = "youtube_extract"
    version = "1.0.0"
    required_fields = ["source_id"]
    output_fields = ["title", "raw_text", "source_metadata"]

    def _download_metadata(self, video_id: str, cookies: CookieManager,
                           proxy: ProxyManager) -> dict:
        """Get video metadata via yt-dlp --dump-json."""
        cmd = [sys.executable, "-m", "yt_dlp",
               "--dump-json", "--skip-download",
               "--no-warnings",
               *cookies.yt_dlp_args(),
               *proxy.yt_dlp_args(),
               "--impersonate", "chrome",
               f"https://www.youtube.com/watch?v={video_id}"]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise ComponentError(f"yt-dlp metadata failed: {result.stderr[:200]}")
        return json.loads(result.stdout)

    def _download_transcript(self, video_id: str, output_dir: Path,
                             cookies: CookieManager, proxy: ProxyManager) -> tuple[str, str]:
        """Download best available transcript. Returns (text_path, json_path)."""
        text_path = output_dir / f"{video_id}.txt"
        json_path = output_dir / f"{video_id}_timed.json"

        # Try subtitle-based transcript first
        cmd = [sys.executable, "-m", "yt_dlp",
               "--skip-download",
               "--write-subs", "--write-auto-subs",
               "--sub-langs", "en,-live_chat",
               "--convert-subs", "srt",
               "--sub-format", "vtt/txt",
               "--no-warnings",
               *cookies.yt_dlp_args(),
               *proxy.yt_dlp_args(),
               "--impersonate", "chrome",
               "-o", str(output_dir / f"{video_id}.%(ext)s"),
               f"https://www.youtube.com/watch?v={video_id}"]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        # Convert SRT/VTT to plain text
        raw_text = ""
        timed_data = []

        # Look for produced subtitle file
        for ext in [".en.vtt", ".en.srt", ".vtt", ".srt"]:
            sub_path = output_dir / f"{video_id}{ext}"
            if sub_path.exists():
                raw_text = self._srt_to_text(sub_path.read_text(encoding="utf-8"))
                # Generate timed segments
                timed_data = self._parse_timed(sub_path.read_text(encoding="utf-8"))
                break

        # Fallback: auto-generated transcript via yt-dlp
        if not raw_text:
            logger.info("[youtube_extract] No subtitles, extracting auto-generated...")
            cmd_fallback = [sys.executable, "-m", "yt_dlp",
                            "--skip-download",
                            "--write-auto-subs",
                            "--sub-langs", "en",
                            "--convert-subs", "srt",
                            "--no-warnings",
                            *cookies.yt_dlp_args(),
                            *proxy.yt_dlp_args(),
                            "--impersonate", "chrome",
                            "-o", str(output_dir / f"{video_id}.%(ext)s"),
                            f"https://www.youtube.com/watch?v={video_id}"]
            subprocess.run(cmd_fallback, capture_output=True, text=True, timeout=60)
            for ext in [".en.vtt", ".en.srt", ".vtt", ".srt"]:
                sub_path = output_dir / f"{video_id}{ext}"
                if sub_path.exists():
                    raw_text = self._srt_to_text(sub_path.read_text(encoding="utf-8"))
                    timed_data = self._parse_timed(sub_path.read_text(encoding="utf-8"))
                    break

        # Write output files
        if raw_text:
            text_path.write_text(raw_text, encoding="utf-8")
        if timed_data:
            json_path.write_text(json.dumps(timed_data, ensure_ascii=False), encoding="utf-8")

        return str(text_path), str(json_path) if timed_data else ""

    @staticmethod
    def _srt_to_text(srt_content: str) -> str:
        """Convert SRT/VTT subtitle content to plain text."""
        lines = []
        for line in srt_content.split("\n"):
            line = line.strip()
            # Skip timestamps, numbers, and empty lines
            if (not line or "-->" in line or
                line.isdigit() or
                line.startswith("WEBVTT") or
                line.startswith("Kind:") or
                line.startswith("Language:")):
                continue
            # Remove VTT tags
            line = re.sub(r'<[^>]+>', '', line)
            if line:
                lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _parse_timed(content: str) -> list[dict]:
        """Parse SRT/VTT into list of {start, end, text}."""
        segments = []
        current = {}
        for line in content.split("\n"):
            line = line.strip()
            if "-->" in line:
                parts = line.split("-->")
                if len(parts) == 2:
                    current = {"start": parts[0].strip(), "end": parts[1].strip(), "text": ""}
            elif line and current:
                if current["text"]:
                    current["text"] += " " + re.sub(r'<[^>]+>', '', line)
                else:
                    current["text"] = re.sub(r'<[^>]+>', '', line)
            elif not line and current.get("text"):
                segments.append(current)
                current = {}
        # Catch last
        if current.get("text"):
            segments.append(current)
        return segments

    def run(self, item: ContentItem, config: dict[str, Any]) -> ContentItem:
        video_id = item.source_id
        output_dir = Path(config.get("output_dir", "output/raw"))

        cookies = CookieManager(config.get("cookies_path"))
        proxy = ProxyManager(http=config.get("proxy_http"))

        # Get metadata
        meta = self._download_metadata(video_id, cookies, proxy)
        item.title = meta.get("title", "")
        uploader = meta.get("uploader", "")
        duration = meta.get("duration", 0)
        item.source_metadata = {
            "author": uploader,
            "channel": uploader,
            "published_at": meta.get("upload_date", ""),
            "duration": duration,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "view_count": meta.get("view_count", 0),
            "description": (meta.get("description", "") or "")[:500],
        }

        # Get transcript
        text_path, json_path = self._download_transcript(video_id, output_dir, cookies, proxy)
        if text_path:
            item.raw_text = Path(text_path).read_text(encoding="utf-8")
        item.artifacts.raw_text = text_path
        item.artifacts.timed_transcript = json_path

        logger.info(f"[youtube_extract] '{item.title}' — {len(item.raw_text)} chars transcript")
        return item


def create():
    return YouTubeExtract()
```

**Step 3: Write youtube_frames.py（合并 diyhub extract_frames.py + ai-crawler youtube_frames.py）**

```python
"""YouTube keyframe extraction — download video, extract step frames via ffmpeg."""
from __future__ import annotations
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ytarticle.core.base import BaseComponent, ComponentError
from ytarticle.core.schema import ContentItem, ImageInfo
from ytarticle.support.cookies import CookieManager
from ytarticle.support.proxy import ProxyManager
from ytarticle.support.llm import call_llm

logger = logging.getLogger("ytarticle.youtube_frames")


class YouTubeFrames(BaseComponent):
    name = "youtube_frames"
    version = "1.0.0"
    required_fields = ["source_id", "article_md"]
    output_fields = ["images"]

    def run(self, item: ContentItem, config: dict[str, Any]) -> ContentItem:
        if item.source.value != "youtube" or not item.source_id:
            return item

        if not shutil.which("ffmpeg"):
            logger.warning("[youtube_frames] ffmpeg not found — skipping")
            return item

        video_id = item.source_id
        output_dir = Path(config.get("output_dir", "output/images")) / video_id
        output_dir.mkdir(parents=True, exist_ok=True)

        cookies = CookieManager(config.get("cookies_path"))
        proxy = ProxyManager(http=config.get("proxy_http"))

        # Detect step timestamps from article + transcript
        timestamps = self._detect_timestamps(item.article_md, item.artifacts.timed_transcript)

        # Download video
        video_path = self._download_video(video_id, output_dir, cookies, proxy)

        if not video_path:
            return item

        # Extract frames
        if timestamps:
            frames = self._extract_frames(video_path, timestamps, output_dir)
        else:
            fallback_count = len(re.findall(r"^## Step \d", item.article_md, re.MULTILINE)) or 8
            frames = self._fallback_frames(video_path, fallback_count, output_dir)

        # Cleanup video
        video_path.unlink(missing_ok=True)

        # Add frame images
        for f in frames:
            item.images.append(ImageInfo(
                path=f["path"],
                alt=f.get("alt", f"Step {f['step']}"),
                step=f["step"],
            ))

        item.artifacts.images_dir = str(output_dir)
        return item

    def _detect_timestamps(self, article_md: str, timed_path: str) -> list[dict]:
        """Use LLM to match article steps to transcript timestamps."""
        if not timed_path or not Path(timed_path).exists():
            return []

        # Extract step-by-step section
        steps_section = ""
        in_steps = False
        for line in article_md.split("\n"):
            if re.match(r"^##\s*Step", line, re.IGNORECASE):
                in_steps = True
            if in_steps and line.startswith("## ") and "Step" not in line:
                break
            if in_steps:
                steps_section += line + "\n"
        if not steps_section.strip():
            return []

        try:
            timed_data = json.loads(Path(timed_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        timed_sample = timed_data[::3][:80]
        system_prompt = (
            "You are a video timestamp detector. Given article steps and transcript "
            "segments with timestamps, output a JSON array of objects with 'step' (int), "
            "'timestamp' (HH:MM:SS), and 'label' (str) fields. "
            "Match each article step to the most relevant transcript timestamp. "
            "Output ONLY the JSON array."
        )
        user_prompt = f"Article steps:\n{steps_section.strip()}\n\nTranscript segments:\n{json.dumps(timed_sample, ensure_ascii=False)}"

        try:
            result = call_llm(system_prompt, user_prompt, max_tokens=2048, temperature=0.3)
            json_match = re.search(r"\[.*\]", result, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.warning(f"[youtube_frames] Timestamp detection failed: {e}")
        return []

    def _download_video(self, video_id: str, output_dir: Path,
                        cookies: CookieManager, proxy: ProxyManager) -> Path | None:
        video_path = output_dir / f"{video_id}.mp4"
        if video_path.exists():
            return video_path

        cmd = [sys.executable, "-m", "yt_dlp",
               "-f", "bestvideo[height<=480]",
               *cookies.yt_dlp_args(),
               *proxy.yt_dlp_args(),
               "--impersonate", "chrome",
               "-o", str(video_path),
               f"https://www.youtube.com/watch?v={video_id}"]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            logger.warning(f"[youtube_frames] Download timed out for {video_id}")
            return None
        except OSError as e:
            logger.warning(f"[youtube_frames] Download error: {e}")
            return None

        if result.returncode != 0 or not video_path.exists():
            logger.warning(f"[youtube_frames] Download failed: {result.stderr[:200]}")
            return None
        return video_path

    def _extract_frames(self, video_path: Path, timestamps: list[dict],
                        output_dir: Path) -> list[dict]:
        ts_pattern = re.compile(r"^\d{2}:\d{2}:\d{2}$")
        frames = []
        for item in timestamps:
            ts = item.get("timestamp", "")
            if not ts_pattern.match(ts):
                continue
            step = item.get("step", len(frames) + 1)
            frame_path = output_dir / f"step_{step:02d}.jpg"
            try:
                result = subprocess.run(
                    ["ffmpeg", "-ss", ts, "-i", str(video_path),
                     "-frames:v", "1", "-q:v", "2",
                     "-filter:v", "scale=800:-1",
                     "-y", str(frame_path)],
                    capture_output=True, text=True, timeout=30)
            except (FileNotFoundError, OSError):
                continue
            if result.returncode == 0 and frame_path.exists():
                frames.append({"path": str(frame_path), "alt": item.get("label", f"Step {step}"), "step": step})
        return frames

    def _fallback_frames(self, video_path: Path, num_steps: int,
                         output_dir: Path) -> list[dict]:
        """Extract frames at regular intervals."""
        # Get video duration
        if not shutil.which("ffprobe"):
            return []
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration", "-of", "json", str(video_path)],
            capture_output=True, text=True, timeout=15)
        try:
            duration = float(json.loads(result.stdout).get("format", {}).get("duration", 600))
        except (json.JSONDecodeError, KeyError, ValueError):
            duration = 600

        interval = duration / (num_steps + 1)
        frames = []
        for i in range(1, num_steps + 1):
            t = int(interval * i)
            mm, ss = divmod(t, 60)
            hh, mm = divmod(mm, 60)
            ts = f"{hh:02d}:{mm:02d}:{ss:02d}"
            frame_path = output_dir / f"step_{i:02d}.jpg"
            try:
                result = subprocess.run(
                    ["ffmpeg", "-ss", ts, "-i", str(video_path),
                     "-frames:v", "1", "-q:v", "2",
                     "-filter:v", "scale=800:-1",
                     "-y", str(frame_path)],
                    capture_output=True, text=True, timeout=30)
            except (FileNotFoundError, OSError):
                continue
            if result.returncode == 0 and frame_path.exists():
                frames.append({"path": str(frame_path), "alt": f"Step {i}", "step": i})
        return frames


def create():
    return YouTubeFrames()
```

**Step 4: Write test_youtube_components.py**

```python
"""Tests for YouTube components."""
import pytest
from ytarticle.core.schema import make_item
from ytarticle.components.sources.youtube_extract import YouTubeExtract


class TestYouTubeExtractComponent:
    def test_component_name_and_version(self):
        comp = YouTubeExtract()
        assert comp.name == "youtube_extract"
        assert comp.version == "1.0.0"

    def test_required_fields(self):
        comp = YouTubeExtract()
        assert "source_id" in comp.required_fields

    def test_create_function(self):
        from ytarticle.components.sources.youtube_extract import create
        comp = create()
        assert comp.name == "youtube_extract"
```

**Step 5: Verify**

```bash
uv run pytest tests/test_youtube_components.py -v
# Expected: 3 passed
uv run pytest tests/ -v
# Expected: 26 passed
```

**Acceptance Criteria:**
1. `youtube_extract` validates required fields
2. `youtube_frames` correctly parses SRT/VTT to text
3. Timestamped transcript parsing produces structured segments
4. `create()` factory returns properly configured component
5. All component tests pass

---

### Task 7: Processor Components (Rewrite + SEO + Render)

**Objective:** 合并 diyhub 和 ai-crawler 的改写、SEO、渲染组件

**Files:**
- Create: `src/ytarticle/components/processors/__init__.py`
- Create: `src/ytarticle/components/processors/ai_rewrite.py`
- Create: `src/ytarticle/components/processors/seo_metadata.py`
- Create: `src/ytarticle/components/processors/html_render.py`
- Create: `tests/test_processor_components.py`

**Step 1: Write ai_rewrite.py**

```python
"""AI rewrite component — transforms raw transcript into structured article."""
from __future__ import annotations
import json
import logging
import re
from pathlib import Path
from typing import Any

from ytarticle.core.base import BaseComponent
from ytarticle.core.schema import ContentItem
from ytarticle.support.llm import call_llm

logger = logging.getLogger("ytarticle.ai_rewrite")

REWRITE_PROMPT = """You are a DIY article writer. Transform the YouTube transcript into a 
step-by-step tutorial article.

Output format:
<!-- METADATA
title: Article H1 Title
difficulty: easy|medium|hard
time: X minutes/hours
cost: $X
materials: item1, item2, item3
-->
## Introduction
[2-3 sentences]

## Step-by-Step
### Step 1: [Title]
[detailed instructions]

### Step 2: [Title]
[detailed instructions]
...

## Tips & Tricks
[2-3 tips]
"""


class AIRewrite(BaseComponent):
    name = "ai_rewrite"
    version = "1.0.0"
    required_fields = ["raw_text", "title"]
    output_fields = ["article_md", "difficulty", "estimated_time", "estimated_cost", "materials"]

    def run(self, item: ContentItem, config: dict[str, Any]) -> ContentItem:
        system_prompt = config.get("prompt", REWRITE_PROMPT)
        user_prompt = f"Title: {item.title}\n\nTranscript:\n{item.raw_text}"

        logger.info(f"[ai_rewrite] Generating article...")
        article = call_llm(system_prompt, user_prompt, max_tokens=8192)

        # Parse metadata block
        meta = self._parse_metadata(article)
        item.difficulty = meta.get("difficulty", "medium")
        item.estimated_time = meta.get("time", "")
        item.estimated_cost = meta.get("cost", "")
        materials_raw = meta.get("materials", "")
        if "," in materials_raw:
            item.materials = [m.strip() for m in materials_raw.split(",") if m.strip()]
        else:
            item.materials = [re.sub(r"^[-*•]\s*", "", m.strip())
                             for m in materials_raw.split("\n") if m.strip()]

        item.article_md = self._strip_metadata(article)
        return item

    @staticmethod
    def _parse_metadata(article: str) -> dict:
        m = re.search(r"<!-- METADATA(.*?)-->", article, re.DOTALL)
        if not m:
            return {}
        meta = {}
        for line in m.group(1).strip().split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip()
        return meta

    @staticmethod
    def _strip_metadata(article: str) -> str:
        return re.sub(r"<!-- METADATA.*?-->", "", article, flags=re.DOTALL).strip()


def create():
    return AIRewrite()
```

**Step 2: Write seo_metadata.py**

```python
"""SEO metadata generation component."""
from __future__ import annotations
import json
import logging
import re
from typing import Any

from ytarticle.core.base import BaseComponent
from ytarticle.core.schema import ContentItem
from ytarticle.support.llm import call_llm

logger = logging.getLogger("ytarticle.seo_metadata")

SEO_PROMPT = """You are an SEO specialist. Given the article, generate metadata in valid JSON:
{
    "title_tag": "Title | SiteName (max 65 chars)",
    "meta_description": "Description (max 155 chars)",
    "url_slug": "/diy/kebab-case-slug",
    "h1": "Main heading"
}
Output ONLY the JSON object."""


class SeoMetadata(BaseComponent):
    name = "seo_metadata"
    version = "1.0.0"
    required_fields = ["article_md"]
    output_fields = ["seo"]

    def run(self, item: ContentItem, config: dict[str, Any]) -> ContentItem:
        article_excerpt = item.article_md[:3000]
        site_name = config.get("site_name", "MakeDIYHub")
        prompt = config.get("prompt", SEO_PROMPT)

        user_prompt = f"Site: {site_name}\n\nArticle excerpt:\n{article_excerpt}"
        logger.info(f"[seo_metadata] Generating SEO metadata...")
        result = call_llm(prompt, user_prompt, max_tokens=1024, temperature=0.3)

        json_match = re.search(r"\{.*\}", result, re.DOTALL)
        if json_match:
            try:
                seo_data = json.loads(json_match.group())
            except json.JSONDecodeError:
                seo_data = {}
        else:
            seo_data = {}

        item.seo.title_tag = self._truncate_title(seo_data.get("title_tag", item.title), site_name)
        item.seo.meta_description = seo_data.get("meta_description", "")[:155]
        item.seo.url_slug = seo_data.get("url_slug", f"/diy/{item.source_id}")
        item.seo.h1 = seo_data.get("h1", item.title)
        return item

    @staticmethod
    def _truncate_title(title: str, site_name: str) -> str:
        suffix = f" | {site_name}"
        if len(title) > 65:
            if suffix in title:
                space = 65 - len(suffix)
                if space > 10:
                    return title[:space].rstrip() + suffix
            return title[:62].rstrip() + "..."
        return title


def create():
    return SeoMetadata()
```

**Step 3: Write html_render.py**

```python
"""HTML render component — pluggable template rendering."""
from __future__ import annotations
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
import markdown as md_lib

from ytarticle.core.base import BaseComponent
from ytarticle.core.schema import ContentItem

logger = logging.getLogger("ytarticle.html_render")


class HtmlRender(BaseComponent):
    name = "html_render"
    version = "1.0.0"
    required_fields = ["article_md", "seo"]
    output_fields = ["artifacts.html_path"]

    def __init__(self):
        super().__init__()
        self._env: Optional[Environment] = None

    def _get_env(self, template_dir: Path) -> Environment:
        if self._env is None:
            self._env = Environment(
                loader=FileSystemLoader(str(template_dir)),
                autoescape=False,
                # Safe: HTML content is generated by Python markdown rendering and
                # Jinja2 templates, not from raw user input. Static HTML output
                # is written to files, not served directly, so XSS is not a concern.
            )
        return self._env

    def _parse_sections(self, md: str) -> tuple[list[dict], list[dict]]:
        """Parse markdown into sections and FAQ items."""
        sections = []
        faq = []
        current = None
        current_lines = []

        for line in md.split("\n"):
            if line.startswith("## "):
                if current:
                    current["body"] = md_lib.markdown("\n".join(current_lines))
                    sections.append(current)
                heading = line[3:].strip()
                current = {"heading": heading, "body": ""}
                current_lines = []
            elif line.startswith("### "):
                if current:
                    current["body"] = md_lib.markdown("\n".join(current_lines))
                    sections.append(current)
                current = {"heading": line[4:].strip(), "body": ""}
                current_lines = []
            else:
                current_lines.append(line)

        if current:
            current["body"] = md_lib.markdown("\n".join(current_lines))
            sections.append(current)

        # Separate FAQ sections
        faq_sections = [s for s in sections if "faq" in s["heading"].lower()]
        sections = [s for s in sections if "faq" not in s["heading"].lower()]
        for fs in faq_sections:
            faq.append({"question": fs["heading"].replace("FAQ:", "").strip(), "answer": fs["body"]})

        return sections, faq

    def run(self, item: ContentItem, config: dict[str, Any]) -> ContentItem:
        # Determine template via template resolver
        template_name = config.get("template", "default/article.html")
        custom_dirs = config.get("template_dirs", [])

        from ytarticle.templates.base import resolve_template
        template_dir, resolved_name = resolve_template(template_name, custom_dirs=custom_dirs)

        env = self._get_env(template_dir)
        template = env.get_template(resolved_name)

        # Parse sections
        sections, faq = self._parse_sections(item.article_md)

        # Build SEO metadata
        site_url = config.get("site_url", "https://example.com")
        url_slug = item.seo.url_slug or f"/diy/{item.source_id}"

        # Build structured data
        howto_schema = self._build_howto_schema(item, sections, site_url, url_slug)
        article_schema = self._build_article_schema(item, site_url, url_slug)
        breadcrumb_schema = self._build_breadcrumb_schema(url_slug)
        faq_schema = self._build_faq_schema(faq, site_url, url_slug) if faq else None

        # Build image map for step sections
        step_imgs = {}
        for img in item.images:
            if img.step > 0 and img.path:
                step_imgs[img.step] = img.path

        # Render
        html = template.render(
            title_tag=item.seo.title_tag or item.title,
            meta_description=item.seo.meta_description,
            url_slug=url_slug,
            title=item.title,
            difficulty=item.difficulty,
            estimated_time=item.estimated_time,
            estimated_cost=item.estimated_cost,
            materials=item.materials,
            sections=sections,
            step_images=step_imgs,
            faq=faq,
            date_published=item.started_at or datetime.now().isoformat(),
            SITE_URL=site_url,
            SITE_NAME=config.get("site_name", "MakeDIYHub"),
            SITE_SLOGAN=config.get("site_slogan", ""),
            howto_schema_json=json.dumps(howto_schema, ensure_ascii=False),
            article_schema_json=json.dumps(article_schema, ensure_ascii=False),
            breadcrumb_schema_json=json.dumps(breadcrumb_schema, ensure_ascii=False),
            faq_schema_json=json.dumps(faq_schema, ensure_ascii=False) if faq_schema else None,
            cover_img=item.artifacts.cover_img or "",
            images=item.images,
        )

        # Write output
        output_dir = Path(config.get("output_dir", "output/html"))
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{item.source_id}.html"
        output_path.write_text(html, encoding="utf-8")
        item.artifacts.html_path = str(output_path)

        logger.info(f"[html_render] Wrote {output_path}")
        return item

    @staticmethod
    def _build_howto_schema(item: ContentItem, sections: list[dict],
                            site_url: str, url_slug: str) -> dict:
        steps = []
        for s in sections:
            if "step" in s["heading"].lower():
                steps.append({
                    "@type": "HowToStep",
                    "position": len(steps) + 1,
                    "name": s["heading"],
                    "text": s["body"],
                })
        schema = {
            "@context": "https://schema.org",
            "@type": "HowTo",
            "name": item.title,
            "description": item.seo.meta_description or "",
            "totalTime": item.estimated_time,
            "cost": item.estimated_cost,
            "step": steps,
        }
        if item.materials:
            schema["supply"] = [{"@type": "HowToSupply", "name": m} for m in item.materials]
        return schema

    @staticmethod
    def _build_article_schema(item: ContentItem, site_url: str, url_slug: str) -> dict:
        return {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": item.title,
            "description": item.seo.meta_description or "",
            "author": {"@type": "Person", "name": item.author or "MakeDIYHub Team"},
            "datePublished": item.started_at or datetime.now().isoformat(),
        }

    @staticmethod
    def _build_breadcrumb_schema(url_slug: str) -> dict:
        return {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": "/"},
                {"@type": "ListItem", "position": 2, "name": "DIY", "item": url_slug},
            ],
        }

    @staticmethod
    def _build_faq_schema(faq: list[dict], site_url: str, url_slug: str) -> dict:
        return {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": f["question"],
                 "acceptedAnswer": {"@type": "Answer", "text": f["answer"]}}
                for f in faq
            ],
        }


def create():
    return HtmlRender()
```

**Step 1: Write failing test**

```python
"""Tests for processor components."""
import pytest
from ytarticle.core.schema import make_item, ContentItem, SeoMetadata
from ytarticle.components.processors.ai_rewrite import AIRewrite
from ytarticle.components.processors.seo_metadata import SeoMetadata as SeoMetadataComp
from ytarticle.components.processors.html_render import HtmlRender


class TestAIRewrite:
    def test_component_name(self):
        comp = AIRewrite()
        assert comp.name == "ai_rewrite"

    def test_parse_metadata(self):
        text = """<!-- METADATA
title: Test Article
difficulty: easy
time: 30 minutes
cost: $10
materials: glue, paper, scissors
-->"""
        meta = AIRewrite._parse_metadata(text)
        assert meta["title"] == "Test Article"
        assert meta["difficulty"] == "easy"

    def test_strip_metadata(self):
        text = "<!-- METADATA\ntitle: Test\n-->\n\n# Article content"
        result = AIRewrite._strip_metadata(text)
        assert "# Article content" in result
        assert "METADATA" not in result


class TestSeoMetadata:
    def test_component_name(self):
        comp = SeoMetadataComp()
        assert comp.name == "seo_metadata"

    def test_truncate_title_short(self):
        result = SeoMetadataComp._truncate_title("Hello World", "TestSite")
        assert "Hello World" in result

    def test_truncate_title_long(self):
        long = "A" * 70
        result = SeoMetadataComp._truncate_title(long, "Site")
        assert len(result) <= 65

    def test_truncate_title_with_suffix(self):
        title = "A" * 50 + " | Site"
        result = SeoMetadataComp._truncate_title(title, "Site")
        assert " | Site" in result


class TestHtmlRender:
    def test_component_name(self):
        comp = HtmlRender()
        assert comp.name == "html_render"

    def test_required_fields(self):
        comp = HtmlRender()
        assert "article_md" in comp.required_fields

    def test_parse_sections(self):
        comp = HtmlRender()
        md = """## Introduction
Hello world.

## Step 1: Setup
Do this.

## FAQ: What is this?
Answer here.
"""
        sections, faq = comp._parse_sections(md)
        assert len(sections) >= 2
        assert len(faq) >= 1
        assert "FAQ" in faq[0]["question"]
```

**Step 5: Verify**

```bash
uv run pytest tests/test_processor_components.py -v
# Expected: 6 passed
uv run pytest tests/ -v
# Expected: 32 passed
```

**Acceptance Criteria:**
1. `AIRewrite` parses METADATA blocks correctly
2. `SeoMetadata` parses LLM JSON output with fallback
3. `HtmlRender` parses markdown into sections + FAQ
4. `HtmlRender` builds HowTo/Article/Breadcrumb schemas
5. Template rendering picks the correct template
6. All 6 new tests pass

---

### Task 8: Content Checker

**Objective:** 基础内容质量检查（从 diyhub content_check.py 简化）

**Files:**
- Create: `src/ytarticle/components/checkers/__init__.py`
- Create: `src/ytarticle/components/checkers/content_check.py`
- Create: `tests/test_checker.py`

**Step 1: Write content_check.py**

```python
"""Content quality checker — verifies minimum quality standards."""
from __future__ import annotations
import logging
from typing import Any

from ytarticle.core.base import BaseComponent
from ytarticle.core.schema import ContentItem

logger = logging.getLogger("ytarticle.content_check")


class ContentCheck(BaseComponent):
    name = "content_check"
    version = "1.0.0"
    required_fields = ["article_md", "seo"]
    output_fields: list[str] = []

    CHECK_TITLE_MIN = 10
    CHECK_TITLE_MAX = 120
    CHECK_DESC_MAX = 160
    CHECK_BODY_MIN_WORDS = 100

    def run(self, item: ContentItem, config: dict[str, Any]) -> ContentItem:
        warnings = []

        # Check article length
        word_count = len(item.article_md.split())
        if word_count < self.CHECK_BODY_MIN_WORDS:
            warnings.append(f"Article too short: {word_count} words (min {self.CHECK_BODY_MIN_WORDS})")

        # Check title
        title = item.seo.title_tag or item.title
        if len(title) < self.CHECK_TITLE_MIN:
            warnings.append(f"Title too short: {len(title)} chars")
        if len(title) > self.CHECK_TITLE_MAX:
            warnings.append(f"Title too long: {len(title)} chars (max {self.CHECK_TITLE_MAX})")

        # Check description
        if item.seo.meta_description:
            if len(item.seo.meta_description) > self.CHECK_DESC_MAX:
                warnings.append(f"Description too long: {len(item.seo.meta_description)} chars")

        # Check difficulty
        if item.difficulty not in ("easy", "medium", "hard"):
            warnings.append(f"Unknown difficulty: {item.difficulty}")

        if warnings:
            for w in warnings:
                logger.warning(f"[content_check] {w}")
        else:
            logger.info("[content_check] All checks passed")

        # Store warnings in metadata (non-blocking)
        item.source_metadata["check_warnings"] = warnings
        return item


def create():
    return ContentCheck()
```

**Step 2: Write test_checker.py**

```python
"""Tests for content checker."""
import pytest
from ytarticle.core.schema import ContentItem, make_item, SeoMetadata
from ytarticle.components.checkers.content_check import ContentCheck


class TestContentCheck:
    def test_component_name(self):
        comp = ContentCheck()
        assert comp.name == "content_check"

    def test_short_article_triggers_warning(self):
        comp = ContentCheck()
        item = make_item("youtube", "123", title="Short")
        item.seo = SeoMetadata(title_tag="Short")
        item.article_md = "Hello"
        result = comp.run(item, {})
        warnings = result.source_metadata.get("check_warnings", [])
        assert any("too short" in w for w in warnings)

    def test_good_article_no_warnings(self):
        comp = ContentCheck()
        item = make_item("youtube", "123", title="Good DIY Project")
        item.seo = SeoMetadata(title_tag="Good DIY Project | Site", meta_description="A desc")
        item.article_md = "Word " * 150
        result = comp.run(item, {})
        warnings = result.source_metadata.get("check_warnings", [])
        assert len(warnings) == 0
```

**Step 3: Verify**

```bash
uv run pytest tests/test_checker.py -v
# Expected: 3 passed
uv run pytest tests/ -v
# Expected: 35 passed
```

**Acceptance Criteria:**
1. ContentCheck warns on short articles (<100 words)
2. ContentCheck warns on short titles (<10 chars)
3. ContentCheck warns on unknown difficulty
4. Good content produces no warnings
5. Checks are non-blocking (warnings in metadata, not status="failed")

---

### Task 9: Templates（可插拔）

**Objective:** 内置 default 和 diyhub 两套模板，TemplateLoader 接口

**Files:**
- Create: `src/ytarticle/templates/__init__.py`
- Create: `src/ytarticle/templates/base.py`
- Create: `src/ytarticle/templates/default/article.html`
- Create: `src/ytarticle/templates/diyhub/article.html`
- Create: `tests/test_templates.py`

**Step 1: Write base.py**

```python
"""Template loader — find and load the right template."""
from __future__ import annotations
from pathlib import Path
from typing import Optional


BUILTIN_TEMPLATES = {
    "default": "default/article.html",
    "diyhub": "diyhub/article.html",
}


def resolve_template(name: str = "default",
                     custom_dirs: Optional[list[str]] = None) -> tuple[Path, str]:
    """Resolve template path and name.

    Returns (template_dir, template_name).
    Search order:
    1. Custom directories (user-provided)
    2. Built-in templates (this package)
    """
    template_name = BUILTIN_TEMPLATES.get(name, name)

    # Check custom dirs first
    if custom_dirs:
        for d in custom_dirs:
            p = Path(d)
            if (p / template_name).exists():
                return p, template_name

    # Fall back to built-in
    pkg_dir = Path(__file__).resolve().parent
    return pkg_dir, template_name


def list_templates() -> list[str]:
    """List available built-in template names."""
    return list(BUILTIN_TEMPLATES.keys())
```

**Step 2: Write default/article.html**

```jinja2
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ title_tag }}</title>
<meta name="description" content="{{ meta_description }}">
<link rel="canonical" href="{{ SITE_URL }}{{ url_slug }}">
<meta property="og:title" content="{{ title_tag }}">
<meta property="og:description" content="{{ meta_description }}">
<meta property="og:type" content="article">
<script type="application/ld+json">{{ howto_schema_json }}</script>
<script type="application/ld+json">{{ article_schema_json }}</script>
<script type="application/ld+json">{{ breadcrumb_schema_json }}</script>
{% if faq_schema_json %}
<script type="application/ld+json">{{ faq_schema_json }}</script>
{% endif %}
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #fff; color: #333; line-height: 1.8; max-width: 800px; margin: 0 auto; padding: 20px; }
h1 { font-size: 2em; margin: 1em 0 0.5em; }
h2 { font-size: 1.5em; margin: 1.5em 0 0.5em; border-bottom: 2px solid #eee; padding-bottom: 0.3em; }
h3 { font-size: 1.2em; margin: 1.2em 0 0.3em; }
p { margin: 0.8em 0; }
img { max-width: 100%; height: auto; border-radius: 8px; margin: 1em 0; }
.info-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; background: #f8f9fa; padding: 16px; border-radius: 12px; margin: 1.5em 0; }
.info-item { text-align: center; }
.info-item .label { font-size: 0.8em; color: #666; }
.info-item .value { font-weight: 600; font-size: 1.1em; }
.materials { background: #fff3e0; padding: 16px; border-radius: 12px; margin: 1.5em 0; }
.materials ul { margin: 0.5em 0 0 1.5em; }
.step-img { width: 100%; max-width: 800px; border-radius: 12px; margin: 12px 0; border: 1px solid #e0e0e0; }
.faq { background: #f1f8e9; padding: 16px; border-radius: 12px; margin: 1.5em 0; }
.faq-item { margin: 0.8em 0; }
.faq-q { font-weight: 600; }
</style>
</head>
<body>
<article>
<h1>{{ title }}</h1>

{% if difficulty or estimated_time or estimated_cost or materials %}
<div class="info-grid">
    {% if difficulty %}<div class="info-item"><div class="label">Difficulty</div><div class="value">{{ difficulty }}</div></div>{% endif %}
    {% if estimated_time %}<div class="info-item"><div class="label">Time</div><div class="value">{{ estimated_time }}</div></div>{% endif %}
    {% if estimated_cost %}<div class="info-item"><div class="label">Cost</div><div class="value">{{ estimated_cost }}</div></div>{% endif %}
</div>
{% endif %}

{% if materials %}
<div class="materials">
    <strong>Materials Needed:</strong>
    <ul>{% for m in materials %}<li>{{ m }}</li>{% endfor %}</ul>
</div>
{% endif %}

{% for section in sections %}
    {% if "Step" in section.heading %}
        <h2>{{ section.heading }}</h2>
        {% if step_images.get(loop.index) %}
        <img src="{{ step_images[loop.index] }}" alt="{{ section.heading }}" class="step-img" loading="lazy">
        {% endif %}
        {{ section.body }}
    {% elif "Introduction" in section.heading or "Tips" in section.heading %}
        <h2>{{ section.heading }}</h2>
        {{ section.body }}
    {% else %}
        <h3>{{ section.heading }}</h3>
        {{ section.body }}
    {% endif %}
{% endfor %}

{% if faq %}
<div class="faq">
    <h2>Frequently Asked Questions</h2>
    {% for item in faq %}
    <div class="faq-item">
        <div class="faq-q">{{ item.question }}</div>
        <div class="faq-a">{{ item.answer }}</div>
    </div>
    {% endfor %}
</div>
{% endif %}
</article>
</body>
</html>
```

**Step 3: Wire diyhub template**

The diyhub template will be copied from the existing one at `~/diyhub/templates/diyhub_article.html`. It's 457 lines with Lora/DM Sans fonts, sage green palette, sticky topbar, etc.

**Step 4: Write test_templates.py**

```python
"""Tests for template system."""
import tempfile
from pathlib import Path
from ytarticle.templates.base import resolve_template, list_templates


class TestTemplateResolver:
    def test_default_template_resolves(self):
        template_dir, template_name = resolve_template("default")
        assert (template_dir / template_name).exists()

    def test_diyhub_template_resolves(self):
        template_dir, template_name = resolve_template("diyhub")
        assert (template_dir / template_name).exists()

    def test_custom_dir_takes_priority(self):
        with tempfile.TemporaryDirectory() as td:
            custom_dir = Path(td)
            tmpl_dir = custom_dir / "custom"
            tmpl_dir.mkdir(parents=True)
            tmpl_file = tmpl_dir / "my_template.html"
            tmpl_file.write_text("<html></html>")

            resolved_dir, resolved_name = resolve_template("custom/my_template.html",
                                                           custom_dirs=[str(custom_dir)])
            assert resolved_name == "custom/my_template.html"

    def test_list_templates(self):
        names = list_templates()
        assert "default" in names
        assert "diyhub" in names
```

**Step 5: Verify**

```bash
cp ~/diyhub/templates/diyhub_article.html src/ytarticle/templates/diyhub/article.html
uv run pytest tests/test_templates.py -v
# Expected: 4 passed
uv run pytest tests/ -v
# Expected: 39 passed
```

**Acceptance Criteria:**
1. `resolve_template("default")` finds a real file
2. `resolve_template("diyhub")` finds a real file
3. Custom dirs override built-in templates
4. `list_templates()` returns available named templates
5. All 4 template tests pass

---

### Task 10: CLI — AI Agent 入口

**Objective:** click CLI 供 AI agent 调用

**Files:**
- Create: `src/ytarticle/cli.py`
- Create: `tests/test_cli.py`

**Step 1: Write cli.py**

```python
"""CLI — AI agent entry point for youtube-to-article pipeline."""
from __future__ import annotations
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import click

from ytarticle.core.schema import ContentItem, make_item
from ytarticle.core.registry import Registry
from ytarticle.core.pipeline import Pipeline


@click.group()
@click.option("--verbose", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx, verbose: bool):
    """youtube-to-article — YouTube video → DIY article pipeline."""
    ctx.ensure_object(dict)
    if verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
    ctx.obj["logger"] = logging.getLogger("cli")


@cli.command()
@click.option("--url", required=True, help="YouTube video URL")
@click.option("--cookies", help="Path to Netscape cookies file")
@click.option("--proxy", help="HTTP proxy (e.g. http://127.0.0.1:8080)")
@click.option("--output-dir", default="output", help="Output directory")
@click.option("--template", default="diyhub", help="HTML template name")
@click.option("--site-name", default="MakeDIYHub", help="Site name for SEO")
@click.option("--site-url", default="https://makediyhub.com", help="Site URL")
@click.option("--json", "json_output", is_flag=True, help="Output JSON result to stdout")
@click.pass_context
def run(ctx, url: str, cookies: Optional[str], proxy: Optional[str],
        output_dir: str, template: str, site_name: str, site_url: str,
        json_output: bool):
    """Run full pipeline on a single YouTube URL."""
    logger = ctx.obj["logger"]

    video_id = _extract_video_id(url)
    if not video_id:
        click.echo("Error: Could not extract video ID from URL", err=True)
        sys.exit(1)

    config = {
        "steps": [
            {"component": "youtube_extract",
             "id": "extract",
             "config": {"output_dir": f"{output_dir}/raw", "cookies_path": cookies or "",
                        "proxy_http": proxy or ""}},
            {"component": "ai_rewrite", "id": "rewrite"},
            {"component": "youtube_frames",
             "id": "frames",
             "config": {"output_dir": f"{output_dir}/images", "cookies_path": cookies or "",
                        "proxy_http": proxy or ""}},
            {"component": "seo_metadata", "id": "seo",
             "config": {"site_name": site_name}},
            {"component": "html_render", "id": "render",
             "config": {"output_dir": f"{output_dir}/html",
                        "template": f"{template}/article.html",
                        "site_url": site_url, "site_name": site_name,
                        "template_dirs": ["templates"]}},
            {"component": "content_check", "id": "check"},
        ]
    }

    item = make_item("youtube", video_id, source_url=url, keyword=site_name)

    pipeline = Pipeline(config)
    result = pipeline.run(item)

    if result.status == "failed":
        click.echo(f"Pipeline failed: {result.error}", err=True)
        sys.exit(1)

    click.echo(f"✅ Article created: {result.artifacts.html_path}")
    click.echo(f"   Title: {result.title}")
    click.echo(f"   Words: {len(result.article_md.split())}")

    if json_output:
        click.echo(json.dumps({
            "status": result.status,
            "title": result.title,
            "html_path": result.artifacts.html_path,
            "article_path": result.artifacts.article_md,
            "word_count": len(result.article_md.split()),
            "difficulty": result.difficulty,
            "images": len(result.images),
        }, indent=2))


def _extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from various URL formats."""
    import re
    patterns = [
        r"(?:youtube\.com/watch\?.*v=)([a-zA-Z0-9_-]{11})",
        r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})",
        r"(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


@cli.command()
def templates():
    """List available templates."""
    from ytarticle.templates.base import list_templates
    for t in list_templates():
        click.echo(t)


if __name__ == "__main__":
    cli()
```

**Step 2: Write test_cli.py**

```python
"""Tests for CLI."""
from click.testing import CliRunner
from ytarticle.cli import cli, _extract_video_id


class TestVideoIdExtraction:
    def test_standard_url(self):
        assert _extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_short_url(self):
        assert _extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_embed_url(self):
        assert _extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        assert _extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_invalid_url(self):
        assert _extract_video_id("https://example.com") is None

    def test_with_params(self):
        assert _extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s") == "dQw4w9WgXcQ"


class TestCLI:
    def test_templates_command(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["templates"])
        assert result.exit_code == 0
        assert "default" in result.output
        assert "diyhub" in result.output
```

**Step 3: Verify**

```bash
uv run pytest tests/test_cli.py -v
# Expected: 7 passed
uv run pytest tests/ -v
# Expected: 46 passed
```

**Acceptance Criteria:**
1. `_extract_video_id()` handles all YouTube URL formats
2. `cli templates` lists available templates
3. `cli run --url ...` accepts all parameters
4. Pipeline errors exit with non-zero code
5. `--json` flag outputs structured JSON to stdout
6. All 7 CLI tests pass

---

### Task 11: 验证：端到端通跑

**Objective:** 确认所有 46+ 测试通过，端到端可运行

**Step 1: Run full test suite**

```bash
cd ~/youtube-to-article
uv run pytest tests/ -v
# Expected: 46 passed (or more)
```

**Step 2: Check CLI help**

```bash
uv run python -m ytarticle.cli --help
uv run python -m ytarticle.cli run --help
```

**Step 3: Initial commit**

```bash
cd ~/youtube-to-article
git add .
git commit -m "feat: initial project scaffolding with full pipeline

- Core: ContentItem schema, BaseComponent, Registry, Pipeline engine
- Sources: youtube_extract (yt-dlp), youtube_frames (ffmpeg)
- Processors: ai_rewrite, seo_metadata, html_render
- Checkers: content_check
- Support: CookieManager, ProxyManager, LLMClient
- Templates: default + diyhub (pluggable)
- CLI: run/templates commands
- Tests: 46+ passing
"
git push origin main
```

**Acceptance Criteria:**
1. All unit tests pass
2. `python -m ytarticle.cli run --help` shows all options
3. `python -m ytarticle.cli templates` lists both templates
4. `import ytarticle` works from any directory
5. Git commit and push succeed
