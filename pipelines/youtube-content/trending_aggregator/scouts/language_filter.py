"""语言检测 — 通过标题/描述推断视频发布地区的语言。

策略（简单关键词匹配，不依赖外部 ML 模型）：
1. 泰文字符 → th（Unicode 范围，100% 准确）
2. 关键词计数 → 匹配多的语种胜出

这是软过滤 —— 主要用于排除明显非目标语种（日语、韩语等）。
短标题（< 10 字）或混合语种标题可能模糊，但不会误杀。
"""

import logging
import re

logger = logging.getLogger(__name__)

THAI_CHARS = re.compile(r"[฀-๿]")

# 英文高频词
EN: set[str] = {
    "the", "this", "that", "these", "those",
    "is", "are", "was", "were", "be", "been",
    "i", "you", "we", "they", "he", "she", "it",
    "my", "your", "our", "their", "its",
    "a", "an", "and", "or", "but", "if",
    "in", "on", "at", "to", "for", "of", "with", "from", "by",
    "not", "no", "will", "can", "do", "does", "did",
    "love", "like", "watch", "best", "new", "top", "great",
    "show", "episode", "season", "trailer",
    "review", "reaction", "update", "news", "list",
    "kdrama", "recommendation",
}

# 印尼语高频词
ID: set[str] = {
    "aku", "saya", "kamu", "kita", "mereka", "kalian", "dia",
    "ini", "itu", "saja", "aja", "sudah", "bisa",
    "tidak", "gak", "enggak", "tak",
    "banget", "sangat", "sekali", "paling",
    "dan", "di", "dari", "dengan", "untuk", "dalam",
    "karena", "tentang", "bagi", "tanpa",
    "yang", "adalah", "juga", "seperti", "kalau", "apakah",
    "nonton", "tonton", "lihat", "bagus", "keren", "seru",
    "terbaru", "terbaik", "terseru",
    "sinopsis", "alur", "karakter", "rekomendasi",
    "drakor", "eps",
}


def _score(text: str) -> tuple[int, int]:
    """返回 (en 得分, id 得分)。"""
    words = text.lower().split()
    en = id_ = 0
    for w in words:
        if w in EN:
            en += 1
        if w in ID:
            id_ += 1
    return en, id_


def detect_language(title: str, description: str = "") -> str | None:
    """检测视频发布语言，返回 iso 代码（id/th/en）或 None。"""
    text = (title.strip() or description.strip())
    if not text:
        return None

    # 1. 泰文字符
    if THAI_CHARS.search(text):
        return "th"

    # 2. 关键词评分
    en, id_ = _score(text)
    if id_ > en and id_ >= 1:
        return "id"
    if en > id_ and en >= 1:
        return "en"
    if en == id_ and id_ >= 1:  # 平局 → 印尼语优先（目标市场）
        return "id"

    return None


def is_target_language(title: str, description: str = "") -> bool:
    return detect_language(title, description) is not None
