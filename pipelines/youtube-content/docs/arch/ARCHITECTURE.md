# YouTube 内容工厂 — 平台架构设计

> **日期:** 2026-07-01
> **状态:** 方案设计
> **定位:** AI Agent 驱动的 YouTube 视频生产全流程平台

---

## 一、平台全景

```
┌──────────────────────────────────────────────────────────────────┐
│                      YouTube 内容工厂                              │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ① Trending Scout        ② AI Studio           ③ SEO Engine     │
│  ┌─────────────────┐    ┌─────────────────┐    ┌──────────────┐ │
│  │ 每日采集热门      │    │ 视频二创+AI配音  │    │ 标题/描述/标签│ │
│  │ YouTube/TikTok/IG│───▶│ Agent 分析趋势   │───▶│ 算法驱动优化  │ │
│  │ → SQLite 存储     │    │ → 生成内容简报   │    │ Hook 生成     │ │
│  └─────────────────┘    │ → 执行剪辑+配音   │    │ 缩略图方案    │ │
│          │              └─────────────────┘    └──────────────┘ │
│          │                       │                     │         │
│          ▼                       ▼                     ▼         │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    ④ Publisher + ⑤ Dashboard                │ │
│  │  ┌──────────────────────┐    ┌──────────────────────────┐   │ │
│  │  │ 定时/手动发布到YouTube│    │ Web 面板：内容日历         │   │ │
│  │  │ 数据追踪 + 反馈闭环   │    │ 任务状态 + 数据看板        │   │ │
│  │  └──────────────────────┘    └──────────────────────────┘   │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  调度层：Hermes Cron + Skills（Agent 自动化）                      │
│  数据层：PostgreSQL + MinIO/S3（视频存储）                         │
│  Web 层：FastAPI + HTMX + Tailwind（管理面板）                     │
└──────────────────────────────────────────────────────────────────┘
```

---

## 二、五大模块详解

### ① Trending Scout — 数据采集层

**定位：** 每日自动运行，作为整条流水线的"眼睛"

| 维度 | 方案 |
|------|------|
| **数据源** | YouTube Trending / TikTok Trending / Instagram Reels |
| **采集频率** | 每日 06:00（在内容生产之前跑） |
| **存储** | PostgreSQL trending_videos 表 |
| **输出** | 每日热门视频 Top 100 + 趋势变化报告 |
| **状态** | ⚡ 方案已完成（~/trending-video-aggregator/PLAN.md） |

**采集的数据：**
```
video_id, platform, title, views, likes, comments, shares,
duration, tags, description, thumbnail_url, published_at, fetched_at
```

**为什么先跑这个：**
- 零依赖，独立模块，跑通后给后续模块提供"今天做什么内容"的数据
- 数据积累后可以做趋势分析（什么话题在上升、什么格式在火）

---

### ② AI Studio — 内容生产层

**定位：** 基于 Trending Scout 数据 + Agent 分析 → 自动生产视频

```
每日流程：
  06:00  Trending Scout 跑完
  07:00  Agent 分析今日热门：
         "今天什么类型视频在火？什么 Hook 在用？什么话题在上升？"
         → 输出《每日内容简报》
  08:00  Agent 决策：
         "基于简报 + 我的素材库，今天生产 X 个视频"
  09:00  执行生产：
         ① 从素材库匹配原视频
         ② AI 识别高光片段
         ③ 剪辑 + AI 配音（ElevenLabs）
         ④ 生成字幕
```

**Agent 分析逻辑（核心差异化）：**

```
Trending 数据 → Agent 分析维度：

  🏷️ 话题趋势
     "过去 7 天 #aitools 标签的视频 views 增长 340%"
     → 建议本周做 AI 工具相关内容

  🎬 格式分析
     "Top 10 视频中 7 个用了 'I tried X for 30 days' 格式"
     → 建议套用这个格式

  🪝 Hook 拆解
     "评分 90+ 的视频 Hook 共同特征：数字+反差+个人经历"
     → 生成同类型 Hook 模板

  📏 时长规律
     "本周热门视频中位数时长：8分32秒"
     → 建议视频控制在 8-10 分钟
```

---

### ③ SEO Engine — 优化层

**定位：** 基于算法数据为每个视频生成最优元数据

**输入：** 视频内容（标题草稿/内容摘要/关键词）
**输出：** 完整 SEO 包

```
SEO Engine 输出：

├── 标题（3 个变体 + CTR 预估分）
│   ├── 变体 A：好奇心驱动型
│   ├── 变体 B：数字+结果型
│   └── 变体 C：问题型
│
├── 描述（符合所有硬性规则）
│   ├── Line 1-3：Hook + 关键词（150 字符可见区）
│   ├── 时间戳章节（3+ 章，0:00 起点）
│   ├── 正文 200-350 词（关键词密度 2-4x）
│   └── CTA + 3 hashtags
│
├── 标签（精准 5-8 个，不超 500 字符）
│   ├── 核心关键词（1-2 个）
│   ├── 相关变体（3-5 个）
│   └── 长尾具体问题（2-3 个）
│
└── 章节标记（keyword-rich labels）
```

**规则引擎数据来源：**
- claude-youtube seo-playbook.md（标题/描述/标签/章节硬规则）
- claude-youtube algorithm-guide.md（CTR 基准、满意度信号权重）
- X 算法源码（排序信号 → SEO 动作映射）

---

### ④ Publisher — 发布层

| 功能 | 方案 |
|------|------|
| **定时发布** | 支持预设时间 + 根据算法高峰时段自动推荐 |
| **YouTube API** | YouTube Data API v3 上传 |
| **发布检查** | 发布前自动校验 SEO 包完整性 |
| **数据追踪** | 发布后 24h/48h/7d 拉取表现数据回写 |

---

### ⑤ Dashboard — Web 管理面板

```
Dashboard 页面结构：

Home
├── 今日概览（采集数/生产数/发布数/总播放）
├── 内容日历（本月发布计划）
└── 告警（异常指标）

Trending
├── 今日热门 Top 50
├── 趋势变化（7 日对比）
└── 话题标签云

Studio
├── 内容简报（Agent 每日分析结果）
├── 视频生产队列
└── 单视频编辑（标题/描述/标签手动调整）

SEO
├── SEO 评分总览
├── 标题 A/B 测试结果
└── 关键词排名追踪

Analytics
├── 频道整体表现
├── 单视频漏斗（曝光→点击→观看→互动）
└── 收入追踪
```

---

## 三、技术架构

```
┌─────────────────────────────────────────────────────────┐
│                    技术栈                                 │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Web 前端:    FastAPI + HTMX + TailwindCSS + Alpine.js  │
│  Web 后端:    Python 3.12 + FastAPI + SQLAlchemy        │
│  数据库:      PostgreSQL（业务数据）+ MinIO/S3（视频）    │
│                                                         │
│  Agent 调度:  Hermes Cron + Skills                      │
│  AI 模型:     Gemini 3.0 Flash（趋势分析/SEO生成）        │
│              ElevenLabs（配音）                          │
│              faster-whisper（字幕）                      │
│              YOLOv8 + MediaPipe（人脸跟踪竖屏裁剪）       │
│                                                         │
│  外部 API:    YouTube Data API v3                       │
│              yt-dlp（下载）                              │
│              FFmpeg（剪辑）                              │
│                                                         │
│  部署:        Docker Compose（单机）                      │
│              或腾讯云 VM（已有）                          │
└─────────────────────────────────────────────────────────┘
```

---

## 四、数据流

```
                    每日定时流水线
                    
  06:00 ───▶ Trending Scout ───▶ trending_videos 表
  07:00 ───▶ Agent 分析 ───────▶ daily_brief 表
  08:00 ───▶ Agent 决策 ───────▶ production_queue 表
  09:00 ───▶ AI Studio 生产 ───▶ videos 表 + MinIO
  10:00 ───▶ SEO Engine ──────▶ video_seo 表
  11:00 ───▶ 人工审核（Dashboard）
  14:00 ───▶ Publisher 发布 ──▶ YouTube
  24h后 ───▶ 数据回写 ────────▶ video_analytics 表
```

---

## 五、数据库核心表

```sql
-- 已有：trending_videos（Trending Scout 产出）

-- 新增：
daily_brief        -- Agent 每日分析结果
production_queue   -- 生产任务队列
videos             -- 生产的视频元数据
video_seo          -- 每个视频的 SEO 包
video_analytics    -- 发布后的表现数据
channels           -- YouTube 频道管理
content_library    -- 素材库索引
```

---

## 六、执行计划

### Phase 0：数据采集先行（1-2 天）⚡ 已方案完成

- Trending Scout 部署运行
- 积累 7 天数据后进入 Phase 1

### Phase 1：SEO Engine + Agent 分析（3-5 天）

- 抽象 claude-youtube 知识 → Hermes Skill
- Agent 自动分析 trending 数据 → 每日简报
- SEO 规则引擎（标题/描述/标签生成）

### Phase 2：AI Studio 生产管线（5-7 天）

- OpenShorts 集成（高光识别 + 剪辑 + 配音）
- WhisperX 字幕生成
- 素材库对接

### Phase 3：Publisher + Dashboard（5-7 天）

- YouTube API 发布
- Web 面板（FastAPI + HTMX）
- 数据追踪

### Phase 4：闭环优化（持续）

- A/B 测试标题
- 基于表现数据调优 Agent 决策
- 扩展到 TikTok/Instagram

---

## 七、与现有项目的关系

| 现有项目 | 在平台中的位置 |
|---------|-------------|
| trending-video-aggregator | ① Trending Scout |
| OpenShorts | ② AI Studio（二创引擎） |
| video_indexer.py | ② 素材库匹配 |
| claude-youtube（抽象版） | ③ SEO Engine |
| X 算法分析 | ③ SEO Engine（规则数据源） |
| baby-harness | Agent 调度框架 |
| crawlweaver | Dashboard 参考架构 |

---

## 八、关键决策待确认

| 决策点 | 选项 | 推荐 |
|--------|------|------|
| 数据库 | SQLite（简单） vs PostgreSQL（扩展） | PostgreSQL（后续分析需求） |
| 视频存储 | 本地磁盘 vs MinIO vs S3 | MinIO（兼容 S3，自部署） |
| 配音方案 | ElevenLabs（最好） vs Edge TTS（免费） | 先 Edge TTS 跑通，后续切 ElevenLabs |
| Agent 框架 | 直接用 Hermes Skills vs baby-harness | Hermes Skills（已有基建） |
| Dashboard | FastAPI+HTMX（轻量） vs Next.js（复杂） | FastAPI+HTMX（匹配你的 crawlweaver 技术栈） |
