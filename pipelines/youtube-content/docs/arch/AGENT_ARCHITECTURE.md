# YouTube Content Factory — Agent 调度层设计（基于 CrewAI）

> **日期:** 2026-07-01
> **状态:** 方案 v3
> **调度引擎:** CrewAI（54k⭐, MIT）
> **原则:** Fork 成熟框架，不改核心，只写 Agent 定义 + 工具集成

---

## 一、为什么选 CrewAI

```
你的流水线：分析 → 决策 → 生产 → SEO → 审核 → 发布

CrewAI 原生匹配：
  Agent = 一个角色（Trend Analyst / Producer / SEO Specialist）
  Task  = 一个步骤（"分析今日热门"）
  Crew  = 一整条流水线（sequential process）
  Tool  = Agent 能调用的外部能力（FFmpeg / yt-dlp / YouTube API）
```

**不需要重新发明调度器——CrewAI 已经把 Agent 编排、状态管理、错误重试做好了。我们只写 Agent 的角色定义 + 工具。**

---

## 二、Agent 团队架构

```
┌─────────────────────────────────────────────────────────────┐
│              YouTube Content Factory Crew                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Crew: Sequential Process（顺序执行）                       │
│                                                             │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│   │ Trend        │───▶│ Content      │───▶│ Production   │ │
│   │ Analyst      │    │ Strategist   │    │ Engineer     │ │
│   │              │    │              │    │              │ │
│   │ 工具:        │    │ 工具:        │    │ 工具:        │ │
│   │ trending_db  │    │ material_lib │    │ whisper      │ │
│   │ web_search   │    │ competitor   │    │ ffmpeg       │ │
│   └──────────────┘    └──────────────┘    │ yolo_crop    │ │
│         │                   │             │ edge_tts     │ │
│         ▼                   ▼             └──────────────┘ │
│   ┌──────────────┐    ┌──────────────┐         │          │
│   │ SEO          │◀───│ Human        │◀────────┘          │
│   │ Specialist   │    │ Reviewer     │                     │
│   │              │    │              │                     │
│   │ 工具:        │    │ 人工审核卡点   │                     │
│   │ seo_rules    │    │ approve/reject│                     │
│   │ title_score  │    └──────────────┘                     │
│   └──────────────┘         │                               │
│         │                  │                               │
│         ▼                  ▼                               │
│   ┌──────────────┐                                         │
│   │ Publisher    │                                         │
│   │              │                                         │
│   │ 工具:        │                                         │
│   │ youtube_api  │                                         │
│   │ scheduler    │                                         │
│   └──────────────┘                                         │
│                                                             │
│   数据层: PostgreSQL（状态+元数据）+ MinIO（视频文件）         │
│   触发层: Hermes Cron（每日 06:00 启动 Crew）                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、6 个 Agent 详细定义

### ① Trend Analyst — 趋势分析员

```python
trend_analyst = Agent(
    role="YouTube Trend Analyst",
    goal="分析今日热门视频数据，识别可复制的内容模式和上升话题",
    backstory=(
        "你是一个资深 YouTube 趋势分析师。"
        "每天你会收到来自 YouTube/TikTok/Instagram 的热门视频数据。"
        "你的任务是找出：什么话题在上升？什么格式在火？什么 Hook 被重复使用？"
        "你的分析将直接指导内容团队今天做什么。"
    ),
    tools=[trending_db_tool, web_search_tool],
    llm="gemini-2.5-flash",  # 或用 deepseek-v4
    verbose=True
)
```

### ② Content Strategist — 内容策略师

```python
content_strategist = Agent(
    role="Content Strategist",
    goal="基于趋势分析 + 素材库，决策今天生产什么视频",
    backstory=(
        "你是内容策略师。你拿到 Trend Analyst 的报告后，"
        "需要结合我们的素材库（content_library），决定："
        "1. 做什么话题（匹配趋势 + 我们有素材）"
        "2. 用什么格式（'I tried X for 30 days' / 'Top 10 X' 等）"
        "3. 用什么 Hook 角度"
        "输出一份《每日内容简报》，每个视频包含：话题、格式、Hook、目标时长。"
    ),
    tools=[material_library_tool, competitor_analysis_tool],
    llm="gemini-2.5-flash",
    verbose=True
)
```

### ③ Production Engineer — 生产工程师

```python
production_engineer = Agent(
    role="Video Production Engineer",
    goal="将内容简报转化为成品视频（剪辑+配音+字幕+竖屏裁剪）",
    backstory=(
        "你是视频生产工程师。你拿到 Content Strategist 的简报后，执行以下步骤："
        "1. 从素材库匹配原视频"
        "2. 调用 Whisper 转文字 + PySceneDetect 场景分割"
        "3. AI 识别高光片段（基于简报指定的 Hook 角度）"
        "4. FFmpeg 精准剪切"
        "5. Edge TTS 配音"
        "6. 字幕烧录 + 竖屏裁剪"
    ),
    tools=[
        whisper_transcribe_tool,
        scene_detect_tool,
        ffmpeg_cut_tool,
        edge_tts_tool,
        subtitle_burn_tool,
        vertical_crop_tool,
    ],
    llm="gemini-2.5-flash",
    verbose=True,
    allow_delegation=False  # 生产步骤不需要再委托
)
```

### ④ SEO Specialist — SEO 优化师

```python
seo_specialist = Agent(
    role="YouTube SEO Specialist",
    goal="为每个视频生成算法优化的标题、描述、标签和章节",
    backstory=(
        "你是 YouTube SEO 专家。你掌握所有最新的算法规则："
        "- 标题 70-100 字符最优（+10-14% CTR）"
        "- 移动端截断 ~40-50 字符，关键词必须前置"
        "- 描述前 150 字符是黄金广告位"
        "- 章节提升 4% AVD、最高 50% 留存"
        "- 标签实际上已死（Gemini 直接看视频内容）"
        "- 点击诱饵会被 AI 惩罚"
        ""
        "你的输出是一个完整的 SEO 包：3 个标题变体（含 CTR 预估分）、"
        "完整描述、精准标签、keyword-rich 章节标记。"
    ),
    tools=[seo_rules_tool, title_scorer_tool, keyword_research_tool],
    llm="gemini-2.5-flash",
    verbose=True
)
```

### ⑤ Human Reviewer — 人工审核

```python
# CrewAI 的 Human-in-the-loop 机制
# 不是 Agent，而是一个流程卡点

review_task = Task(
    description="审核 SEO 优化后的完整视频包，确认后发布",
    agent=seo_specialist,  # SEO 完成后触发审核
    human_input=True,       # ← 这里暂停，等人点"确认"
    expected_output="人工确认后的最终发布包"
)
```

### ⑥ Publisher — 发布员

```python
publisher = Agent(
    role="YouTube Publisher",
    goal="将审核通过的视频发布到 YouTube，并跟踪表现数据",
    backstory=(
        "你是发布专员。拿到审核通过的视频 + SEO 包后："
        "1. 通过 YouTube Data API 上传视频"
        "2. 设置标题/描述/标签/缩略图"
        "3. 按最佳发布时间排期"
        "4. 发布后 24h/48h/7d 拉取表现数据回写数据库"
    ),
    tools=[youtube_upload_tool, analytics_tracker_tool],
    llm="gemini-2.5-flash",
    verbose=True
)
```

---

## 四、Crew 装配（完整流水线）

```python
# factory/crew.py

from crewai import Agent, Task, Crew, Process

# ======== Agent 定义（见上） ========
# trend_analyst, content_strategist, production_engineer,
# seo_specialist, publisher

# ======== Task 链 ========

task_analyze_trends = Task(
    description=(
        "1. 从 trending_videos 表读取今日热门 Top 100\n"
        "2. 识别：上升话题、热门格式、高频 Hook 模式\n"
        "3. 与过去 7 天数据对比，找出增长最快的话题\n"
        "4. 输出《今日趋势报告》（Markdown）"
    ),
    expected_output="今日趋势报告（含话题排名、格式分析、Hook 拆解）",
    agent=trend_analyst,
    output_file="output/daily_trend_report.md"
)

task_create_brief = Task(
    description=(
        "1. 基于《今日趋势报告》，结合素材库 inventory\n"
        "2. 决策今天生产 N 个视频\n"
        "3. 每个视频指定：话题、格式、Hook 角度、目标时长\n"
        "4. 输出《每日内容简报》"
    ),
    expected_output="每日内容简报（每个视频含话题/格式/Hook/时长/素材路径）",
    agent=content_strategist,
    context=[task_analyze_trends],  # ← 依赖上一个 task 的输出
    output_file="output/daily_content_brief.md"
)

task_produce_videos = Task(
    description=(
        "对《每日内容简报》中的每个视频：\n"
        "1. 匹配素材（material_library）\n"
        "2. 转文字（whisper）\n"
        "3. 场景分割 + AI 选高光\n"
        "4. FFmpeg 剪切\n"
        "5. Edge TTS 配音\n"
        "6. 字幕烧录 + 竖屏裁剪\n"
        "输出每个视频的文件路径"
    ),
    expected_output="生产完成的视频文件列表",
    agent=production_engineer,
    context=[task_create_brief],
    output_file="output/production_log.json"
)

task_generate_seo = Task(
    description=(
        "为每个生产完成的视频生成 SEO 包：\n"
        "1. 3 个标题变体（含 CTR 预估）\n"
        "2. 完整描述（前 150 字黄金区 + 章节 + CTA）\n"
        "3. 精准标签（5-8 个，总长 <500 字符）\n"
        "4. Keyword-rich 章节标记（3+ 章，0:00 起点）"
    ),
    expected_output="每个视频的完整 SEO 包",
    agent=seo_specialist,
    context=[task_produce_videos],
    output_file="output/seo_packages.json"
)

task_human_review = Task(
    description=(
        "请审核以下 SEO 优化后的视频包。\n"
        "确认标题是否吸引人、描述是否符合规则、标签是否精准。\n"
        "审核通过后视频将自动发布。"
    ),
    expected_output="确认发布或退回修改",
    agent=seo_specialist,
    context=[task_generate_seo],
    human_input=True  # ← 人工审核卡点
)

task_publish = Task(
    description=(
        "1. 通过 YouTube API 上传视频\n"
        "2. 设置标题/描述/标签\n"
        "3. 按最佳时间排期（默认：目标时区 14:00）\n"
        "4. 初始状态设为 'private'（可后续手动公开）"
    ),
    expected_output="每个视频的 YouTube video_id",
    agent=publisher,
    context=[task_human_review],
    output_file="output/publish_log.json"
)

# ======== Crew 装配 ========

content_factory_crew = Crew(
    agents=[
        trend_analyst,
        content_strategist,
        production_engineer,
        seo_specialist,
        publisher,
    ],
    tasks=[
        task_analyze_trends,
        task_create_brief,
        task_produce_videos,
        task_generate_seo,
        task_human_review,
        task_publish,
    ],
    process=Process.sequential,  # 顺序执行
    verbose=True,
    memory=True,                 # CrewAI 管理跨 task 记忆
)
```

---

## 五、工具层（Agent 能调用的外部能力）

CrewAI 的 Tool 就是一个 Python 函数 + 描述。直接写：

```python
# factory/tools.py

from crewai.tools import tool

@tool("YouTube Trending Database")
def trending_db_tool(days: int = 1) -> str:
    """查询 PostgreSQL 中的 trending_videos 表，返回今日热门数据"""
    # ... SQL 查询
    return json.dumps(results)

@tool("Whisper Transcribe")
def whisper_transcribe_tool(video_path: str) -> str:
    """用 faster-whisper 将视频转为带时间戳的文字"""
    import subprocess
    result = subprocess.run([
        "faster-whisper", video_path, 
        "--output_format", "srt"
    ], capture_output=True, text=True)
    return result.stdout

@tool("FFmpeg Clip")
def ffmpeg_cut_tool(video_path: str, start: float, end: float, output: str) -> str:
    """用 FFmpeg 精准剪切视频片段"""
    subprocess.run([
        "ffmpeg", "-i", video_path,
        "-ss", str(start), "-to", str(end),
        "-c", "copy", output, "-y"
    ])
    return output

@tool("Edge TTS Dub")
def edge_tts_tool(text: str, voice: str = "en-US-JennyNeural", output: str = "dub.mp3") -> str:
    """用 Edge TTS 生成配音音频"""
    subprocess.run([
        "edge-tts", "--text", text,
        "--voice", voice,
        "--write-media", output
    ])
    return output

@tool("YouTube Upload")
def youtube_upload_tool(video_path: str, title: str, description: str, tags: list) -> str:
    """通过 YouTube Data API v3 上传视频"""
    # ... YouTube API 调用
    return video_id

@tool("Title Scorer")
def title_scorer_tool(title: str) -> dict:
    """基于 SEO 规则给标题打分"""
    score = 0
    issues = []
    
    # 长度检查
    if 70 <= len(title) <= 100:
        score += 20
    elif len(title) < 40:
        issues.append("太短：移动端截断前 40-50 字符是关键")
    
    # 数字检查
    if any(c.isdigit() for c in title):
        score += 15  # 数字提升 20-30% CTR
    
    # 强力词检查
    power_words = ["secret", "mistake", "tried", "actually", "never", "every"]
    if any(w in title.lower() for w in power_words):
        score += 15
    
    # ... 更多规则
    
    return {"score": score, "max": 100, "issues": issues}

# ... 更多工具：PySceneDetect, YOLO crop, SEO rules, etc.
```

---

## 六、触发方式

```
Hermes Cron（每日 06:00）
    │
    ▼
python factory/run.py
    │
    ▼
content_factory_crew.kickoff()
    │
    ▼
Sequential execution:
  Trend Analyst → Strategist → Producer → SEO → [Human Review] → Publisher
```

---

## 七、和现有项目的关系

```
youtube-content-factory/
├── factory/                    ← 🆕 自研（基于 CrewAI）
│   ├── crew.py                 ← Agent 定义 + Crew 装配
│   ├── tools.py                ← 工具函数（调开源模型）
│   └── run.py                  ← 入口（Hermes Cron 触发）
│
├── trending_aggregator/        ← 已有（Trending Scout）
│   └── ...                     ← 填 trending_videos 表
│
├── dashboard/                  ← 🆕 FastAPI + HTMX
│   └── ...                     ← Web 管理面板
│
├── skills/                     ← Hermes Skills
│   └── seo-engine/             ← SEO 规则（参考 claude-youtube）
│
├── models/                     ← SQLAlchemy models
│   └── ...                     ← PostgreSQL Schema
│
└── ARCHITECTURE.md             ← 架构文档（本文件）
```

---

## 八、代码量估算

| 模块 | 代码量 | 说明 |
|------|--------|------|
| Agent 定义 + Crew 装配 | ~200 行 | 6 个 Agent + 6 个 Task |
| 工具函数 | ~300 行 | ~15 个 @tool 函数 |
| 数据库 models | ~100 行 | SQLAlchemy |
| Dashboard | ~800 行 | FastAPI + HTMX |
| **合计（自研）** | **~1400 行** | |
| CrewAI | 0 行 | pip install |
| 开源模型 | 0 行 | faster-whisper / FFmpeg / Edge TTS |

**核心自研代码 ~1400 行，其余全是拼装成熟组件。**
