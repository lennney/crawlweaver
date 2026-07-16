# YouTube-to-Article 初始项目搭建 — 第二轮审查

**审查日期:** 2026-06-24
**审查人:** Hermes Agent
**审查范围:** CRITICAL/IMPORTANT 修复验证 + 回归检查
**基准:** 上一轮审查 `docs/plans/initial-project-review.md`

---

## 裁决: REQUEST_CHANGES

所有 7 项 CRITICAL/IMPORTANT 修复已正确应用。但修复过程中引入了 **1 个新的严重问题** — 运行时崩溃。建议修复后再执行。

---

## CRITICAL 修复验证

### ✅ CRITICAL #1: TDD 顺序声明

**位置:** 计划第 3 行

**修复前:** `按计划逐任务执行，每个任务 TDD`（含糊，与实际步骤矛盾）

**修复后:**
> **提取已有代码的任务**先验证（确认已有代码正确）→ 写测试 → 移植实现。**新增逻辑的任务**严格 TDD：先写测试（RED）→ 写实现（GREEN）→ 验证。

**验证:** 明确区分了两类任务的工作流，任务步骤与声明一致。✅ 修复完成。

---

### ✅ CRITICAL #2: `cover_img` 字段缺失

**位置:** `schema.py` — `ArtifactPaths` 定义

**修复前:** 缺少 `cover_img` 字段，但 `html_render.py` 引用了 `item.artifacts.cover_img`，会导致 `AttributeError`。

**修复后:**
```python
class ArtifactPaths(BaseModel):
    raw_text: str = ""
    article_md: str = ""
    html_path: str = ""
    images_dir: str = ""
    timed_transcript: str = ""
    cover_img: str = ""       # ← 新增
```

**验证:** 
- `ArtifactPaths` (第 250-256 行) 包含 `cover_img: str = ""` ✅
- `html_render.py` (第 1891 行) 使用 `cover_img=item.artifacts.cover_img or ""` ✅

---

## IMPORTANT 修复验证

### ✅ IMPORTANT #1: 目录树中的幽灵文件 `support/http.py`

**位置:** 目录结构部分 (第 56-60 行)

**修复前:** 目录树列出了 `support/http.py`，但没有任何任务创建它。

**修复后:** `support/` 下仅包含 `__init__.py`、`cookies.py`、`proxy.py`、`llm.py`，无 `http.py`。

**验证:** ✅ 已移除。

---

### ✅ IMPORTANT #2: 模板解析逻辑重复

**位置:** `html_render.py` — `run()` 方法

**修复前:** `HtmlRender.run()` 有自定义模板搜索逻辑，未使用 `templates.base.resolve_template()`。

**修复后:**
```python
from ytarticle.templates.base import resolve_template
template_dir, resolved_name = resolve_template(template_name, custom_dirs=custom_dirs)
```

**验证:** 
- `html_render.py` 第 1844-1845 行调用 `resolve_template` ✅
- `templates/base.py` 第 2219-2239 行定义了 `resolve_template()` ✅
- `test_templates.py` (第 2351-2375 行) 测试了 resolve_template 功能 ✅

---

### ✅ IMPORTANT #3: CLI `--config` 选项

**位置:** `cli.py`

**修复前:** `@click.group()` 上定义了 `--config` 选项，但 `run` 命令硬编码了 pipeline 配置，忽略了该选项。

**修复后:**
- `@click.group()` (第 2423 行) 只有 `--verbose` 选项，无 `--config`。
- `run` 命令 (第 2436 行) 使用显式参数 (`--url`、`--cookies`、`--proxy`、`--output-dir`、`--template`、`--site-name`、`--site-url`、`--json`)。
- Pipeline 配置硬编码在 `run()` 中 (第 2457-2477 行)，配置直接来自 CLI 参数。

**验证:** ✅ 清理完成，无误导性 `--config` 选项。

---

### ✅ IMPORTANT #4: 跨模块测试导入

**位置:** `test_pipeline.py` / `conftest.py`

**修复前:** `test_pipeline.py` 使用 `from tests.test_base import DummyComponent`（测试模块间相互导入）。

**修复后:** 
- `DummyComponent` 定义在 `conftest.py` (第 702-711 行)
- `conftest.py` 提供了 `dummy_comp` fixture (第 714-716 行)
- `test_pipeline.py` 使用 fixture 参数 `dummy_comp` (第 744 行)

**验证:** ✅ 消除了跨模块导入，使用了标准 pytest fixture 模式。

---

### ✅ IMPORTANT #5: `TestSeoMetadata` 测试覆盖

**位置:** `test_processor_components.py`

**修复前:** 完全没有 `SeoMetadata` 组件的测试。

**修复后:** `TestSeoMetadata` 类 (第 2004-2021 行) 包含 4 个测试：

| 测试方法 | 验证内容 |
|---------|---------|
| `test_component_name` | 组件名称 `== "seo_metadata"` |
| `test_truncate_title_short` | 短标题保留原文 |
| `test_truncate_title_long` | 长标题截断到 ≤65 字符 |
| `test_truncate_title_with_suffix` | 截断保留 `| SiteName` 后缀 |

**验证:** ✅ 4 个测试覆盖了核心功能。

---

## 🔴 新发现的重要问题

### 🔴 NEW CRITICAL #3: `meta_keywords` 从 SeoMetadata 删除但 html_render 仍引用它

**位置:**
- `schema.py` 第 259-263 行: `SeoMetadata` 模型定义
- `html_render.py` 第 1873 行: `meta_keywords=item.seo.meta_keywords`

**问题:** 上一轮审查的 MINOR #1 建议移除 `meta_keywords` 字段（Google 自 2009 年起不再使用）。修复从 `SeoMetadata` 模型中删除了该字段，但没有更新 `html_render.py` 中的引用。

- `SeoMetadata` (第 259-263 行) 只有: `title_tag`、`meta_description`、`url_slug`、`h1`
- `html_render.py` 第 1873 行: `meta_keywords=item.seo.meta_keywords`

**影响:** 运行时，`item.seo.meta_keywords` 将引发 `AttributeError`，因为：
1. `meta_keywords` 不是 `SeoMetadata` 的已定义字段
2. `seo_metadata` 组件的 `run()` 方法（第 1722-1744 行）也未设置该属性
3. Pydantic v2 默认不允许访问未定义的字段属性

**修复建议（二选一）：**
- **方案 A（推荐）：** 从 `html_render.py` 第 1873 行移除 `meta_keywords=item.seo.meta_keywords`，同时从 SEO_PROMPT (第 1711 行) 移除 `meta_keywords` 行，避免浪费 LLM token。
- **方案 B：** 将 `meta_keywords: str = ""` 添加回 `SeoMetadata` 模型，保持向后兼容。

---

## 其他观察

### ✅ 附带修复的次要问题

| 上一轮 MINOR # | 问题 | 状态 |
|---------------|------|------|
| #5 | `markdown-it-py` 依赖重复 | ✅ 已移除（仅保留 `markdown`） |
| #7 | `pyproject.toml` 缺少 CLI 入口点 | ✅ 已添加（第 137-138 行） |

### ⚠️ 未修复的次要问题（可接受）

| 上一轮 MINOR # | 问题 | 说明 |
|---------------|------|------|
| #2 | `CookieManager._validated` 未使用 | 不影响运行，可在后续优化 |
| #3 | `ProxyManager.requests_kwargs()` 未使用 | 仅增加少量无用代码 |
| #4 | `keyword` 字段功能弱化 | 预留字段，不造成问题 |
| #6 | Task 7 粒度过大（4 文件 + 1 测试） | 功能上可接受，可在执行中拆分 |
| #8 | `autoescape=False` | 当前安全因为输出是生成而非用户输入 |

---

## 总结

| 类别 | 数量 |
|------|------|
| ✅ CRITICAL 修复通过 | 2 |
| ✅ IMPORTANT 修复通过 | 5 |
| 🔴 新 CRITICAL 问题 | 1 |
| **总体裁决** | **REQUEST_CHANGES** |

**核心问题:** `meta_keywords` 从 schema 移除但 `html_render.py` 仍引用它 → 运行时崩溃。

**建议操作:** 在开始执行之前解决 NEW CRITICAL #3（方案 A 较优 — 同时移除 LLM prompt 和 render 引用，节省 token 并消除运行时错误）。
