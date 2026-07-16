# YouTube-to-Article 初始项目搭建 — 实施计划审查

**审查日期:** 2026-06-24
**审查人:** Hermes Agent
**审查文件:** `docs/plans/2026-06-24-initial-project.md`
**审查范围:** 12 项标准 + 常见陷阱检查

---

## 裁决: REQUEST_CHANGES

计划整体质量很高，代码完整、命令精确、目录结构清晰。但存在 **1 个严重问题**（运行时崩溃）、**1 个流程问题**（TDD 声明与实现不符）和若干重要/次要问题。**建议修正后再执行。**

---

## 12 项标准检查清单

| # | 标准 | 状态 | 备注 |
|---|------|------|------|
| 1 | 任务粒度 2-5 分钟 | ⚠️ 部分达标 | 多数任务合理，但 Task 7（4 个实现文件）偏大 |
| 2 | 文件路径精确 | ✅ | 每个文件路径完整精确 |
| 3 | 代码示例完整可复制 | ✅ | 所有文件内容完整、测试完备 |
| 4 | 命令精确带预期输出 | ✅ | 每条命令附带 `# Expected:` 注释 |
| 5 | TDD（测试先于代码） | ❌ **严重不符** | 见下方 Critical Issue #1 |
| 6 | 验证步骤 | ✅ | 每任务有 Verify 命令 + Acceptance Criteria |
| 7 | DRY 不重复 | ⚠️ 可接受 | 代码是从 ai-crawler/diyhub 抽取，重复不可避免 |
| 8 | YAGNI 不过度设计 | ⚠️ 有少量冗余 | 见下方 Important/Minor 问题 |
| 9 | 无缺失上下文 | ❌ **有遗漏** | 见 Critical Issue #2 |
| 10 | 向后兼容 | N/A | 新仓库 |
| 11 | 任务依赖顺序正确 | ✅ | 拓扑序合理 |
| 12 | 集成干净 | ⚠️ 有小问题 | 见下方问题清单 |

---

## 严重问题 (必须修复)

### 🔴 CRITICAL #1: TDD 声明与实现不符（Criterion 5）

**位置:** 计划第 3 行 `> **For Hermes:** 按计划逐任务执行，每个任务 TDD`

**问题:** 计划宣称每个任务都遵循 TDD（测试驱动开发），但实际每个任务的步骤都是：
1. Step 1: 写实现代码
2. Step 2: 写测试代码
3. Step 3: 验证

TDD 的核心是 **测试先行**（Red-Green-Refactor）。正确的 TDD 流程应该是：
1. Step 1: 写测试（预期失败）
2. Step 2: 写最简实现让测试通过
3. Step 3: 验证 + 重构

**建议:** 将每个任务的 Step 1 和 Step 2 交换顺序。先写测试，再写实现。或者，如果计划的意思是 "每个代码产出任务都要配套测试"，则应将声明改为 `每个任务都有完整测试（代码+测试成对产出）`，避免误解。

---

### 🔴 CRITICAL #2: `cover_img` 字段在 `ArtifactPaths` 中缺失，但 `html_render.py` 引用了它

**位置:**
- `html_render.py` 第 1836 行: `cover_img=item.artifacts.cover_img or ""`
- `schema.py` 第 249-254 行: `ArtifactPaths` 定义

**问题:** 新的 `ArtifactPaths` 模型（第 249-254 行）定义了以下字段：
```python
class ArtifactPaths(BaseModel):
    raw_text: str = ""
    article_md: str = ""
    html_path: str = ""
    images_dir: str = ""
    timed_transcript: str = ""
```

但 `html_render.py` 第 1836 行调用了 `item.artifacts.cover_img`，该字段并不存在于新的 `ArtifactPaths` 中。运行时将抛出 `AttributeError`。

原有 `ai-crawler/schema.py` 的 `ArtifactPaths` 确实包含 `cover_img` 字段，但抽取时遗漏了。

**建议:**
- 方案 A: 在 `ArtifactPaths` 中添加 `cover_img: str = ""`
- 方案 B: 从 `html_render.py` 中移除 `cover_img` 引用（如果不需要）

---

## 重要问题 (建议修复)

### 🟠 IMPORTANT #1: `support/http.py` 在目录结构中声明但从未创建

**位置:** 目录结构第 58-60 行: `support/http.py`

**问题:** 目录树中列出了 `src/ytarticle/support/http.py`（`HTTP 请求封装（UA + 头 + 重试）`），但没有任何一个任务实际创建这个文件。它成了一个幽灵文件——在结构中存在，但从未实现，也没有被任何组件引用。

**建议:** 要么添加一个任务来创建 `http.py`（如果项目确实需要），要么从目录结构中删除该行。

---

### 🟠 IMPORTANT #2: 模板解析逻辑重复 — `templates/base.py` vs `html_render.py`

**位置:**
- `templates/base.py`: `resolve_template()` 函数
- `html_render.py` 第 1770-1790 行: 自定义模板搜索逻辑

**问题:** 计划建立了 `templates/base.py` 作为模板系统的统一入口 (`resolve_template`)，但 `HtmlRender.run()` 完全没有使用它，而是重新实现了自己的模板搜索逻辑（遍历 `search_paths` 列表寻找模板文件）。两套逻辑功能重叠但实现不同。

**建议:** 让 `HtmlRender.run()` 调用 `templates.base.resolve_template()` 来解析模板路径，消除重复逻辑。

---

### 🟠 IMPORTANT #3: CLI `--config` 选项被定义但被 `run` 命令忽略

**位置:**
- `cli.py` 第 2352 行: `@click.option("--config", default="config.yaml")`
- `cli.py` 第 2388-2408 行: `run()` 命令硬编码了 pipeline 配置

**问题:** `cli` 组定义了一个 `--config` 选项，但 `run` 命令内部直接硬编码了完整的 pipeline 配置（steps 列表），完全忽略了用户提供的 `--config` 文件。这会误导用户以为可以传入自定义配置。

**建议:**
- 方案 A: 移除 `--config` 选项（如果不需要自定义配置）
- 方案 B: 让 `run` 命令支持从 YAML 加载配置，仅在没有配置文件时使用默认硬编码配置

---

### 🟠 IMPORTANT #4: `test_pipeline.py` 从另一个测试模块导入

**位置:** `test_pipeline.py` 第 721 行: `from tests.test_base import DummyComponent`

**问题:** 测试模块之间相互导入是一种不良实践。`DummyComponent` 在两个测试文件中都被需要，本应放在 `conftest.py` 作为共享 fixture。

**建议:** 将 `DummyComponent` 移到 `conftest.py` 或 `tests/helpers.py`，然后通过 fixture 注入。

---

### 🟠 IMPORTANT #5: `SeoMetadata` 处理器组件没有测试覆盖

**位置:** `test_processor_components.py`

**问题:** Task 7 的验收标准第 2 条要求 "SeoMetadata parses LLM JSON output with fallback"，但 `test_processor_components.py` 中只有 `TestAIRewrite` 和 `TestHtmlRender`，没有 `TestSeoMetadata` 类。`SeoMetadata` 组件完全没有测试覆盖。

**建议:** 在 `test_processor_components.py` 中添加 `TestSeoMetadata` 测试类，至少测试：
- 组件名称和版本
- JSON 解析
- 标题截断逻辑 (`_truncate_title`)
- fallback 行为（当 LLM 返回无效 JSON 时）

---

## 次要问题 (建议优化)

### 🔵 MINOR #1: `meta_keywords` 字段已过时

**位置:** `schema.py` 第 264 行

**问题:** `SeoMetadata` 包含 `meta_keywords: str = ""`。Google 自 2009 年起就不再使用 meta keywords 标签进行排名。添加此字段会：
1. 增加不必要的 schema 复杂度
2. 浪费 LLM token 生成这个值
3. 在 `default/article.html` 模板第 2183 行输出该标签

**建议:** 移除或标记为弃用。

---

### 🔵 MINOR #2: `CookieManager._validated` 字段未使用

**位置:** `cookies.py` 第 813 行

**问题:** `__init__` 中设置了 `self._validated = False`，但该属性在整个类中从未被读取或修改。每次调用 `is_valid` 都会重新解析整个文件。

**建议:** 要么实现缓存逻辑（读取一次后标记 `_validated = True`），要么移除未使用的字段。

---

### 🔵 MINOR #3: `ProxyManager.requests_kwargs()` 已定义但从未被调用

**位置:** `proxy.py` 第 883-887 行

**问题:** 该方法是用于 `requests` 库的代理配置，但项目中的所有组件都使用 `yt-dlp`（通过 subprocess）而非 `requests`。项目中也没有任何地方引用 `requests` 包。

**建议:** 如果确认不会使用 `requests`，可以移除该方法。否则添加对应的依赖和用例。

---

### 🔵 MINOR #4: `keyword` 字段功能弱化

**位置:** `schema.py` 第 286 行

**问题:** 新的 `ContentItem.task_id()` 返回 `{source.value}_{source_id}`（简化版），不再包含 `keyword`。但 `ContentItem` 仍然保留了 `keyword` 字段。在 `ai-crawler` 原版中，`keyword` 是 `task_id()` 的一部分且用于持久化分片，在新项目中 `keyword` 除了被 `make_item()` 初始化时设置外，没有任何功能用途。

**建议:** 如果确实不需要 `keyword` 的分片/分类功能，可考虑移除该字段以简化 schema。

---

### 🔵 MINOR #5: `markdown` 和 `markdown-it-py` 依赖重复

**位置:** `pyproject.toml` 第 127、129 行

**问题:** 计划同时引入了 `markdown>=3.0` 和 `markdown-it-py>=3.0`。`html_render.py` 使用 `import markdown as md_lib`（即 `markdown` 包），没有使用 `markdown-it-py`。两个包功能重叠（都是 Markdown 渲染器）。

**建议:** 只保留实际使用的 `markdown`，移除 `markdown-it-py`。

---

### 🔵 MINOR #6: Task 7 粒度过大

**位置:** Task 7（Processor Components）

**问题:** Task 7 需要创建 **4 个实现文件** + **1 个测试文件**（`ai_rewrite.py`, `seo_metadata.py`, `html_render.py`, `test_processor_components.py`，加上 `processors/__init__.py`），远超 2-5 分钟的粒度。相比之下，Task 8 只有 2 个文件，Task 9 有 5 个文件但模板文件是静态 HTML。

**建议:** 将 Task 7 拆分为 2-3 个子任务（例如：7a=AIRewrite, 7b=SeoMetadata, 7c=HtmlRender+Templates），每个子任务配额不超过 2 个实现文件。

---

### 🔵 MINOR #7: `pyproject.toml` 缺少 CLI 入口点

**位置:** `pyproject.toml` 第 115-131 行

**问题:** 验证步骤使用 `uv run python -m ytarticle.cli`，但没有定义 `[project.scripts]` 入口点。更标准的做法是添加：
```toml
[project.scripts]
ytarticle = "ytarticle.cli:cli"
```
这样用户/agent 可以直接运行 `ytarticle run --url ...`。

---

### 🔵 MINOR #8: `html_render.py` 使用 `autoescape=False`

**位置:** `html_render.py` 第 1728 行

**问题:** 注释说 "Safe: HTML is generated by Python, not user input"，但 `item.article_md` 是由 LLM 生成的文本，经过 markdown 转换后包含 HTML。LLM 输出不可完全信任设置为 `autoescape=False` 会增加 XSS 风险（尤其如果未来 HTML 被托管在网站上）。

**建议:** 使用 `autoescape=True`（Jinja2 默认），或至少添加注释说明为什么可以安全地禁用转义。

---

## 总结

| 类别 | 数量 |
|------|------|
| 🔴 严重 (Critical) | 2 |
| 🟠 重要 (Important) | 5 |
| 🔵 次要 (Minor) | 8 |
| **总计** | **15** |

**核心缺陷:** TDD 声明与实现不符（CRITICAL #1）+ 运行时崩溃风险（CRITICAL #2）。

**建议操作:** 修复两个严重问题后，酌情处理重要问题（特别是 IMPORTANT #5 — 组件无测试覆盖），即可开始执行。
