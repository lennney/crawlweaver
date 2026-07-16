# HANDOVER — YouTube Content Factory

> 最后更新: 2026-07-10

## 当前状态

**Phase 0-2 完工。** 账号追踪模块已扩展至 3 平台（YouTube + TikTok + Instagram），每日运营报表功能上线，cron 定时调度已配置。

## 本次会话完成

### 每日运营报表（daily-report）

- 列顺序对齐 (新)社媒运营情况-每日记录更新.xlsx 格式
- 发布时间 | 视频方向 | 相关剧集 | 视频内容 | 浏览量 | 点赞 | 点赞率 | 粉丝数 | 涨粉
- 支持 `--date YYYY-MM-DD` 指定日期，`--format csv` 导出

### 粉丝数追踪

| 平台 | 方案 |
|------|------|
| YouTube | yt-dlp `channel_follower_count`（无 `--flat-playlist`） |
| TikTok | HTTP 抓取 `__UNIVERSAL_DATA_FOR_REHYDRATION__` 中的 `followerCount` |
| Instagram | `/api/v1/users/web_profile_info/` → `edge_followed_by.count` |

每次 `fetch` 自动写 `AccountSnapshot` 快照，`daily-report` 计算涨粉 = 今天 - 昨天。

### Instagram 接入

- 无需登录，使用 Instagram 公开 API（`X-IG-App-ID: 936619743392459`）
- `/api/v1/users/web_profile_info/` → 粉丝数
- `/api/v1/feed/user/{id}/` → 帖子列表（发布时间、播放量、点赞、标题）
- 4 个 IG 账号已录入 `data/accounts_template.csv`

### 定时调度

- Cron: `0 9 * * * cd ... && fetch --detailed && daily-report >> /tmp/social-report.log`
- 每天 9:00 AM 自动采集 + 出报表

### 数据模型更新

- `TrackedAccount` + `follower_count`
- `VideoSnapshot` + `username` + `published_at`
- 新增 `AccountSnapshot` 表（account_id, follower_count, fetched_at）

## 账号矩阵

| 地区 | YouTube | TikTok | Instagram | Facebook |
|------|---------|--------|-----------|----------|
| 印尼 | sunnymov-u4h | dana22274 | drama4u_04, movieboxofficial_indonesia | ❌ |
| 菲律宾 | UCGmjHvPxv37vzWvYTS0aZPg, lucy-q8h8x | sunny99392, what2watch30 | luc_ydrama, movieboxph_official | ❌ |
| 尼日利亚 | UCa6Bihg4VEeA6RQbKmpBrhQ | nigmomce74v(已弃) | willie_liya(404) | ❌ |

**已自动化**: 12 个（4 YT + 3 TK + 4 IG）
**暂不支持**: Facebook — 无公开 API，HTML 全客户端渲染

## 已接入爬虫工具

| 数据源 | 采集器 | 引擎 | 状态 |
|--------|--------|------|------|
| YouTube | `scout.py` → `_run_ytdlp()` | yt-dlp | ✅ |
| TikTok | `scout.py` → `_run_ytdlp()` | yt-dlp | ✅ |
| Instagram | `scout.py` → `_fetch_instagram_account()` | 公开 API (urllib) | ✅ |
| Facebook | — | 不可行 | ❌ |

## 已知限制

- TikTok hashtag API 被反爬拦截（status 10201），改用 trending feed + 关键词匹配
- YouTube 部分频道无 /videos tab，自动回退到频道主页
- 视频方向（韩剧/本地剧/图文）无法自动识别，默认 `-`
- Instagram `willie_liya` 返回 404
- TikTok `nigmomce74v` 账号已失效
- 涨粉需要连续两天采集，第一天无数据时显示 `-`
