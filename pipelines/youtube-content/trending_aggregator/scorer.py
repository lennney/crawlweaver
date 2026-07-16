"""热度分算法 — 含时间衰减。

权重：views 50 / likes 25 / comments 15 / shares 10 = 100。
互动率上限按现实爆款设：likes 10%、comments 5%、shares 5%。
时间衰减：24h 内无衰减，之后 7 天半衰期。
"""


def compute_trend_score(
    views: int,
    likes: int,
    comments: int,
    shares: int,
    published_days_ago: float = 0,
) -> float:
    """计算热度分 (0-100)。

    - views: 百万播放 = 满分（50 分）
    - likes/views: 上限 10%（25 分）
    - comments/views: 上限 5%（15 分）
    - shares/views: 上限 5%（10 分）
    - 时间衰减: 24h 内无衰减，之后 7 天半衰期
    """
    views = max(views, 1)

    views_score = min(views / 1_000_000, 1.0) * 50
    likes_score = min(likes / views / 0.10, 1.0) * 25
    comments_score = min(comments / views / 0.05, 1.0) * 15
    shares_score = min(shares / views / 0.05, 1.0) * 10

    raw = views_score + likes_score + comments_score + shares_score

    # 时间衰减：24h 内无衰减，之后 7 天半衰期
    if published_days_ago > 1:
        decay = 2.0 ** (-(published_days_ago - 1) / 7)
        raw *= decay

    return round(raw, 1)


if __name__ == "__main__":
    # ponytail: 自检 — 4 个边界值，跑通即算法自洽
    assert 0 <= compute_trend_score(1, 0, 0, 0, 0) <= 35
    assert 80 <= compute_trend_score(5_000_000, 500_000, 50_000, 100_000, 1) <= 100
    fresh = compute_trend_score(1_000_000, 100_000, 10_000, 20_000, 0)
    old = compute_trend_score(1_000_000, 100_000, 10_000, 20_000, 14)
    assert old < fresh * 0.5
    assert compute_trend_score(100_000, 10_000, 1_000, 2_000, 0) == compute_trend_score(
        100_000, 10_000, 1_000, 2_000, 0.5
    )
    print("scorer self-check ok")
