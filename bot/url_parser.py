"""URL 智能解析 — 从 URL 自动推断来源/关键词/内容类型。

Factor #4: Tool is just structured output from deterministic code + LLM fallback.
"""

import re
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class URLInfo:
    source: str  # youtube / web / reddit / twitter / wechat / zhihu
    keyword: str  # AI-guessed keyword or empty
    content_type: str  # Beginner Guide / Product / News / etc.
    confidence: float  # 0.0 - 1.0


SOURCE_PATTERNS = [
    ("youtube", [r"youtube\.com/watch", r"youtu\.be/"]),
    ("reddit", [r"reddit\.com/r/"]),
    ("twitter", [r"twitter\.com/\w+/status", r"x\.com/\w+/status"]),
    ("wechat", [r"mp\.weixin\.qq\.com/s/"]),
    ("zhihu", [r"zhuanlan\.zhihu\.com/p/", r"zhihu\.com/question/"]),
]


def _match_source(url: str) -> str | None:
    """规则匹配来源 — 覆盖 80% 的 URL."""
    url_lower = url.lower()
    for source, patterns in SOURCE_PATTERNS:
        for pat in patterns:
            if re.search(pat, url_lower):
                return source
    return None


def _guess_keyword_from_url(url: str) -> str:
    """从 URL 路径提取关键词（启发式）."""
    try:
        path = urlparse(url).path
        # 取最后一段路径作为关键词候选
        slug = path.rstrip("/").split("/")[-1]
        # 清理 slug
        slug = re.sub(r"[_-]", " ", slug)
        slug = re.sub(r"\?.*", "", slug)
        slug = re.sub(r"\.(html|md|php)$", "", slug)
        if len(slug) > 3 and len(slug) < 80:
            return slug
    except Exception:
        pass
    return ""


def parse_url(url: str, use_llm: bool = False) -> URLInfo:
    """解析 URL，返回来源、关键词、内容类型。

    Args:
        url: 要解析的 URL
        use_llm: 如果为 True，用 LLM 兜底规则匹配失败的情况
    """
    source = _match_source(url) or "web"
    keyword = _guess_keyword_from_url(url)
    content_type = "Beginner Guide"

    confidence = 0.9 if source != "web" else 0.5

    # YouTube 特殊处理：用 LLM 提取真实标题和描述
    if use_llm and source == "web" and not keyword:
        # 兜底：用 LLM 从 URL 推断
        try:
            import html
            from urllib.request import urlopen

            resp = urlopen(url, timeout=10)
            text = resp.read(4096).decode("utf-8", errors="ignore")
            title_match = re.search(r"<title>(.*?)</title>", text, re.I)
            if title_match:
                keyword = html.unescape(title_match.group(1))[:80]
                confidence = 0.7
        except Exception:
            pass

    return URLInfo(
        source=source,
        keyword=keyword,
        content_type=content_type,
        confidence=confidence,
    )
