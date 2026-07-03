"""飞书卡片 JSON 模板 — 交互卡片 / 进度卡片 / 结果卡片。

飞书卡片是 JSON DSL，无需任何前端框架。
参考: https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/card-components
"""

from typing import Any


def confirm_card(url: str, source: str, keyword: str, confidence: float) -> dict:
    """确认爬取卡片 — 带确认/取消按钮."""
    source_emoji = {
        "youtube": "🎬",
        "web": "🌐",
        "reddit": "💬",
        "twitter": "🐦",
        "wechat": "📱",
        "zhihu": "📖",
    }.get(source, "🌐")

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"{source_emoji} 爬取确认"},
            "template": "blue",
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    {"is_short": False, "text": {"tag": "lark_md", "content": f"**来源:** {source}"}},
                    {"is_short": False, "text": {"tag": "lark_md", "content": f"**关键词:** {keyword or '（自动识别中）'}"}},
                    {"is_short": False, "text": {"tag": "lark_md", "content": f"**URL:** {url[:80]}{'...' if len(url) > 80 else ''}"}},
                    {"is_short": False, "text": {"tag": "lark_md", "content": f"**识别置信度:** {confidence:.0%}"}},
                ],
            },
            {"tag": "hr"},
            {
                "tag": "note",
                "elements": [{"tag": "plain_text", "content": "点击确认后开始爬取，过程约 1-3 分钟"}],
            },
        ],
    }


def progress_card(url: str, step: str, progress_pct: int) -> dict:
    """进度卡片 — 实时更新."""
    steps_emoji = {
        "extract": "📥 正在提取内容...",
        "rewrite": "✍️ AI 改写中...",
        "seo": "🔍 生成 SEO 元数据...",
        "render": "🎨 渲染 HTML...",
        "verify": "✅ 质量自检...",
        "fix": "🔧 自动修复中...",
    }
    step_text = steps_emoji.get(step, f"⏳ {step}...")
    short_url = url[:50] + "..." if len(url) > 50 else url

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "📦 正在爬取..."},
            "template": "blue",
        },
        "elements": [
            {"tag": "markdown", "content": f"**{short_url}**"},
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": step_text},
            },
            {
                "tag": "progress",
                "value": progress_pct,
                "max": 100,
            },
        ],
    }


def result_card(url: str, title: str, word_count: int, score: int, result_url: str) -> dict:
    """结果卡片 — 爬取完成."""
    score_emoji = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "✅ 爬取完成"},
            "template": "green",
        },
        "elements": [
            {"tag": "markdown", "content": f"**{title or url[:60]}**"},
            {"tag": "hr"},
            {
                "tag": "div",
                "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"📝 **{word_count}** 字"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"{score_emoji} 质量 **{score}**/100"}},
                ],
            },
            {"tag": "hr"},
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "📄 查看详情"},
                        "type": "primary",
                        "url": result_url,
                    },
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "📊 写入多维表格"},
                        "type": "default",
                        "value": {"action": "save_bitable", "url": url, "title": title},
                    },
                ],
            },
        ],
    }


def error_card(url: str, error_msg: str) -> dict:
    """错误卡片."""
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "❌ 爬取失败"},
            "template": "red",
        },
        "elements": [
            {"tag": "markdown", "content": f"**{url[:60]}**"},
            {"tag": "hr"},
            {"tag": "markdown", "content": f"错误: {error_msg}"},
        ],
    }


def timeout_card(url: str, task_id: str) -> dict:
    """超时卡片 — 爬取超过 5 分钟未完成."""
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "⏰ 爬取超时"},
            "template": "yellow",
        },
        "elements": [
            {"tag": "markdown", "content": f"**{url[:60]}**\n\n爬取超过 5 分钟未完成，可能页面较大或网络较慢。"},
            {"tag": "hr"},
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "🔄 重试"},
                        "type": "primary",
                        "value": {"action": "retry", "task_id": task_id},
                    },
                ],
            },
        ],
    }
