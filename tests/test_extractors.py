"""Tests for Sprint 5: Multi-source extractors.

Tests URL detection and source routing without making real HTTP requests.
For the actual extractors, we test with mocked responses.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from state import make_state, Source
from tools.extract import detect_source, extract


# --- detect_source tests ---

def test_detect_youtube():
    assert detect_source("https://www.youtube.com/watch?v=abc123") == "youtube"
    assert detect_source("https://youtu.be/abc123") == "youtube"
    assert detect_source("https://m.youtube.com/watch?v=abc123") == "youtube"


def test_detect_twitter():
    assert detect_source("https://twitter.com/elonmusk/status/123") == "twitter"
    assert detect_source("https://x.com/elonmusk/status/123") == "twitter"
    assert detect_source("https://mobile.twitter.com/user/status/456") == "twitter"


def test_detect_wechat():
    assert detect_source("https://mp.weixin.qq.com/s/abc123") == "wechat"
    assert detect_source("https://mp.weixin.qq.com/s?__biz=abc&mid=123") == "wechat"


def test_detect_zhihu():
    assert detect_source("https://zhuanlan.zhihu.com/p/123456") == "zhihu"
    assert detect_source("https://www.zhihu.com/p/123456") == "zhihu"
    assert detect_source("https://zhihu.com/question/123/answer/456") == "zhihu"


def test_detect_reddit():
    assert detect_source("https://www.reddit.com/r/python/comments/abc/test") == "reddit"


def test_detect_web_fallback():
    assert detect_source("https://example.com/article") == "web"
    assert detect_source("https://blog.example.com/post/123") == "web"


# --- Source enum tests ---

def test_source_enum_new_values():
    """Sprint 5: New source types exist in enum."""
    assert Source.TWITTER.value == "twitter"
    assert Source.WECHAT.value == "wechat"
    assert Source.ZHIHU.value == "zhihu"


def test_source_from_string():
    """Source can be created from string values."""
    assert Source("twitter") == Source.TWITTER
    assert Source("wechat") == Source.WECHAT
    assert Source("zhihu") == Source.ZHIHU


# --- Extract routing tests ---

def test_extract_routes_twitter():
    """extract() should call Twitter extractor for Source.TWITTER."""
    state = make_state("https://twitter.com/user/status/123", source="twitter", keyword="test")

    mock_fn = MagicMock()
    with patch.dict("sys.modules", {"tools.extractors.twitter": MagicMock(extract_twitter=mock_fn)}):
        result = extract(state)
        mock_fn.assert_called_once()


def test_extract_routes_wechat():
    """extract() should call WeChat extractor for Source.WECHAT."""
    state = make_state("https://mp.weixin.qq.com/s/abc", source="wechat", keyword="test")

    mock_fn = MagicMock()
    with patch.dict("sys.modules", {"tools.extractors.wechat": MagicMock(extract_wechat=mock_fn)}):
        result = extract(state)
        mock_fn.assert_called_once()


def test_extract_routes_zhihu():
    """extract() should call Zhihu extractor for Source.ZHIHU."""
    state = make_state("https://zhuanlan.zhihu.com/p/123", source="zhihu", keyword="test")

    mock_fn = MagicMock()
    with patch.dict("sys.modules", {"tools.extractors.zhihu": MagicMock(extract_zhihu=mock_fn)}):
        result = extract(state)
        mock_fn.assert_called_once()


# --- Twitter extractor unit tests ---

def test_twitter_extract_tweet_id():
    """Tweet ID extraction from various URL formats."""
    from tools.extractors.twitter import _extract_tweet_id

    assert _extract_tweet_id("https://twitter.com/elonmusk/status/1234567890") == "1234567890"
    assert _extract_tweet_id("https://x.com/user/status/9876543210") == "9876543210"
    assert _extract_tweet_id("https://mobile.twitter.com/user/status/111") == "111"
    assert _extract_tweet_id("https://twitter.com/user/statuses/222") == "222"
    assert _extract_tweet_id("https://example.com/not-a-tweet") is None


def test_twitter_extract_via_oembed():
    """Twitter extractor should try oembed API first."""
    from tools.extractors.twitter import extract_twitter

    state = make_state("https://twitter.com/test/status/123", source="twitter", keyword="test")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "html": '<p>Hello world <a href="https://t.co/abc">link</a></p>',
        "author_name": "testuser",
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_resp):
        extract_twitter(state)

    assert "Hello world" in state.raw_text
    assert "testuser" in state.title
    assert state.source_metadata["method"] == "oembed"


# --- WeChat extractor unit tests ---

def test_wechat_extract_basic():
    """WeChat extractor should parse article from HTML."""
    from tools.extractors.wechat import extract_wechat

    state = make_state("https://mp.weixin.qq.com/s/abc123", source="wechat", keyword="test")

    html = """
    <html>
    <head><meta property="og:title" content="测试文章"></head>
    <body>
        <h1 id="activity-name">测试文章标题</h1>
        <a id="js_name">公众号名称</a>
        <div id="js_content">
            <p>第一段内容</p>
            <p>第二段内容</p>
        </div>
        <span id="publish_time">2024-01-15</span>
    </body>
    </html>
    """
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.status_code = 200
    mock_resp.encoding = "utf-8"
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_resp):
        extract_wechat(state)

    assert "测试文章标题" in state.title
    assert "第一段内容" in state.raw_text
    assert "第二段内容" in state.raw_text
    assert state.source_metadata["author"] == "公众号名称"


def test_wechat_rejects_non_wechat_url():
    """WeChat extractor should reject non-WeChat URLs."""
    from tools.extractors.wechat import extract_wechat

    state = make_state("https://example.com/article", source="web", keyword="test")
    try:
        extract_wechat(state)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Not a WeChat article URL" in str(e)


# --- Zhihu extractor unit tests ---

def test_zhihu_url_detection():
    """Zhihu URL pattern detection."""
    from tools.extractors.zhihu import _is_article_url, _is_answer_url

    assert _is_article_url("https://zhuanlan.zhihu.com/p/123456")
    assert _is_article_url("https://www.zhihu.com/p/123456")
    assert not _is_article_url("https://zhihu.com/question/123/answer/456")

    assert _is_answer_url("https://zhihu.com/question/123/answer/456")
    assert _is_answer_url("https://www.zhihu.com/question/123/answer/456")
    assert not _is_answer_url("https://zhuanlan.zhihu.com/p/123")


def test_zhihu_extract_article_via_api():
    """Zhihu article extraction via API."""
    from tools.extractors.zhihu import extract_zhihu

    state = make_state("https://zhuanlan.zhihu.com/p/123456", source="zhihu", keyword="test")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "title": "知乎专栏文章",
        "content": "<p>文章内容</p><p>第二段</p>",
        "author": {"name": "作者"},
        "voteup_count": 100,
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_resp):
        extract_zhihu(state)

    assert state.title == "知乎专栏文章"
    assert "文章内容" in state.raw_text
    assert state.source_metadata["method"] == "api"
    assert state.source_metadata["author"] == "作者"
