"""Tag 搜索采集器测试。

测试核心逻辑（阈值判断、tag 匹配），不依赖网络/API。
"""
from trending_aggregator.scouts.tiktok_tag import TikTokTagScout
from trending_aggregator.scouts.youtube_tag import YouTubeTagScout


class TestTikTokTagScout:
    def setup_method(self):
        self.scout = TikTokTagScout(tags=["test"], language_filter=False)

    def test_threshold_pass_views(self):
        v = {"views": 600_000, "likes": 0, "title": "", "description": "",
             "published_at": None, "id": "t:1", "url": "", "tags": [],
             "comments": 0, "shares": 0, "duration": 0, "thumbnail_url": ""}
        assert self.scout._pass_threshold(v)

    def test_threshold_pass_likes(self):
        v = {"views": 0, "likes": 50_000, "title": "", "description": "",
             "published_at": None, "id": "t:1", "url": "", "tags": [],
             "comments": 0, "shares": 0, "duration": 0, "thumbnail_url": ""}
        assert self.scout._pass_threshold(v)

    def test_threshold_fail(self):
        v = {"views": 1000, "likes": 100, "title": "", "description": "",
             "published_at": None, "id": "t:1", "url": "", "tags": [],
             "comments": 0, "shares": 0, "duration": 0, "thumbnail_url": ""}
        assert not self.scout._pass_threshold(v)

    def test_keyword_match_in_tags(self):
        v = {"tags": ["movie", "funny"], "description": "something else",
             "title": "", "views": 0, "likes": 0, "published_at": None,
             "id": "t:1", "url": "", "comments": 0, "shares": 0,
             "duration": 0, "thumbnail_url": ""}
        # keyword "test" in tags
        self.scout.keywords = {"funny"}
        assert self.scout._matches_keywords(v)

    def test_keyword_match_in_desc(self):
        v = {"tags": [], "description": "this is a test video",
             "title": "", "views": 0, "likes": 0, "published_at": None,
             "id": "t:1", "url": "", "comments": 0, "shares": 0,
             "duration": 0, "thumbnail_url": ""}
        self.scout.keywords = {"test"}
        assert self.scout._matches_keywords(v)


class TestYouTubeScout:
    def test_normalize(self):
        s = YouTubeTagScout(tags=["movie"], language_filter=False)
        data = {
            "id": "abc123",
            "title": "Test Video",
            "webpage_url": "https://youtube.com/watch?v=abc123",
            "view_count": 1_000_000,
            "like_count": 50_000,
            "comment_count": 1000,
            "duration": 300,
            "tags": ["movie"],
            "description": "A test video",
            "thumbnail": "https://example.com/thumb.jpg",
            "upload_date": "20250601",
        }
        v = s._normalize(data)
        assert v["id"] == "youtube:abc123"
        assert v["views"] == 1_000_000
        assert v["likes"] == 50_000
