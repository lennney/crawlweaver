"""TDD: 先写测试，后写实现"""
from trending_aggregator.scorer import compute_trend_score


class TestTrendScore:
    """热度分算法测试"""

    def test_zero_views_returns_minimal_score(self):
        score = compute_trend_score(
            views=1, likes=0, comments=0, shares=0,
            published_days_ago=0
        )
        assert 0 <= score <= 35

    def test_viral_video_scores_high(self):
        score = compute_trend_score(
            views=5_000_000, likes=500_000, comments=50_000, shares=100_000,
            published_days_ago=1
        )
        assert 80 <= score <= 100

    def test_time_decay(self):
        """7 天前的视频应该有显著衰减"""
        fresh = compute_trend_score(
            views=1_000_000, likes=100_000, comments=10_000, shares=20_000,
            published_days_ago=0
        )
        old = compute_trend_score(
            views=1_000_000, likes=100_000, comments=10_000, shares=20_000,
            published_days_ago=14
        )
        assert old < fresh * 0.5  # 14 天后衰减超过 50%

    def test_no_decay_within_24h(self):
        fresh = compute_trend_score(
            views=100_000, likes=10_000, comments=1_000, shares=2_000,
            published_days_ago=0
        )
        day1 = compute_trend_score(
            views=100_000, likes=10_000, comments=1_000, shares=2_000,
            published_days_ago=0.5  # 12 小时
        )
        assert day1 == fresh  # 24h 内无衰减
