from __future__ import annotations

import asyncio

import pytest

from src.platforms.x import x_extractor
from src.platforms.x.x_extractor import XExtractor


# ---------------------------------------------------------------------------
# handles()
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://x.com/elonmusk/status/1234567890", True),
        ("https://www.x.com/elonmusk/status/1234567890", True),
        ("https://twitter.com/elonmusk/status/1234567890", True),
        ("https://www.twitter.com/elonmusk/status/1234567890", True),
        ("https://x.com/i/web/status/1234567890", True),
        ("https://twitter.com/i/web/status/1234567890", True),
        ("https://example.com/x.com/foo", False),
        ("https://github.com/x.com/foo", False),
        ("https://mp.weixin.qq.com/s/example", False),
    ],
)
def test_handles(url, expected):
    assert x_extractor.handles(url) is expected


# ---------------------------------------------------------------------------
# _extract_tweet_id()
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url, expected_id",
    [
        ("https://x.com/elonmusk/status/1234567890", "1234567890"),
        ("https://x.com/elonmusk/status/1234567890?s=20", "1234567890"),
        ("https://twitter.com/i/web/status/1234567890", "1234567890"),
    ],
)
def test_extract_tweet_id(url, expected_id):
    extractor = XExtractor()
    assert extractor._extract_tweet_id(url) == expected_id


def test_extract_tweet_id_invalid_url():
    extractor = XExtractor()
    with pytest.raises(ValueError, match="no tweet ID found"):
        extractor._extract_tweet_id("https://x.com/elonmusk")


# ---------------------------------------------------------------------------
# _parse_oembed_html()
# ---------------------------------------------------------------------------
def test_parse_oembed_html_full():
    html = """
    <blockquote class="twitter-tweet">
      <p lang="en" dir="ltr">Just launched Starship!
      <a href="https://t.co/abc123">pic.twitter.com/abc123</a></p>
      &mdash; Elon Musk (@elonmusk)
      <a href="https://twitter.com/elonmusk/status/1234567890">March 14, 2024</a>
    </blockquote>
    """
    extractor = XExtractor()
    result = extractor._parse_oembed_html(html)

    assert "Just launched Starship!" in result["text"]
    assert "[pic.twitter.com/abc123](https://t.co/abc123)" in result["text"]
    assert result["author_name"] == "Elon Musk"
    assert result["author_handle"] == "elonmusk"
    assert result["published_at"] == "March 14, 2024"
    assert result["tweet_url"] == "https://twitter.com/elonmusk/status/1234567890"


def test_parse_oembed_html_no_p_tag_fallback():
    """When <p> tag is missing, text should be empty but other fields extracted."""
    html = """
    <blockquote class="twitter-tweet">
      &mdash; Unknown Author (@unknown)
      <a href="https://x.com/unknown/status/123">Jan 1, 2024</a>
    </blockquote>
    """
    extractor = XExtractor()
    result = extractor._parse_oembed_html(html)

    assert result["text"] == ""
    assert result["author_name"] == "Unknown Author"
    assert result["author_handle"] == "unknown"
    assert result["published_at"] == "Jan 1, 2024"


def test_parse_oembed_html_chinese():
    html = """
    <blockquote class="twitter-tweet">
      <p lang="zh" dir="ltr">今天天气真好！
      <a href="https://t.co/xyz">pic.twitter.com/xyz</a></p>
      &mdash; 张三 (@zhangsan)
      <a href="https://x.com/zhangsan/status/999">2024年5月18日</a>
    </blockquote>
    """
    extractor = XExtractor()
    result = extractor._parse_oembed_html(html)

    assert "今天天气真好！" in result["text"]
    assert result["author_name"] == "张三"
    assert result["author_handle"] == "zhangsan"
    assert result["published_at"] == "2024年5月18日"


# ---------------------------------------------------------------------------
# _synthesize_title()
# ---------------------------------------------------------------------------
def test_synthesize_title_short():
    extractor = XExtractor()
    title = extractor._synthesize_title("Elon Musk", "Short tweet")
    assert title == "Elon Musk: Short tweet"


def test_synthesize_title_long():
    extractor = XExtractor()
    text = "This is a very long tweet that exceeds sixty characters by a lot actually"
    title = extractor._synthesize_title("Elon Musk", text)
    # Should truncate to ~60 chars and append "..."
    assert title.startswith("Elon Musk: This is a very long tweet that exceeds sixty")
    assert title.endswith("...")
    assert len(title) < 80  # author + ": " + 60 chars + "..."


def test_synthesize_title_no_author():
    extractor = XExtractor()
    title = extractor._synthesize_title("", "Some text")
    assert title == "X Post: Some text"


# ---------------------------------------------------------------------------
# _html_to_markdown()
# ---------------------------------------------------------------------------
def test_html_to_markdown_links_and_breaks():
    extractor = XExtractor()
    html = '<p>Hello <a href="https://example.com">world</a>!<br>Second line</p>'
    result = extractor._html_to_markdown(html)
    # get_text(" ", strip=True) inserts spaces between text nodes
    assert result == "Hello [world](https://example.com) ! Second line"


def test_html_to_markdown_strip_other_tags():
    extractor = XExtractor()
    html = '<p><strong>Bold</strong> and <em>italic</em></p>'
    result = extractor._html_to_markdown(html)
    assert result == "Bold and italic"


# ---------------------------------------------------------------------------
# extract() — mocked oEmbed API
# ---------------------------------------------------------------------------
def _mock_fetch_oembed(*args, **kwargs):
    return {
        "url": "https://x.com/elonmusk/status/1234567890",
        "author_name": "Elon Musk",
        "author_url": "https://x.com/elonmusk",
        "html": (
            '<blockquote class="twitter-tweet">'
            '<p lang="en" dir="ltr">Just launched Starship!</p>'
            '&mdash; Elon Musk (@elonmusk) '
            '<a href="https://twitter.com/elonmusk/status/1234567890">March 14, 2024</a>'
            '</blockquote>\n'
        ),
        "width": 550,
        "height": None,
        "type": "rich",
        "cache_age": "1800",
        "provider_name": "X",
        "provider_url": "https://x.com",
        "version": "1.0",
    }


def test_extract_full_pipeline(monkeypatch):
    async def mock_fetch(self, url):
        return _mock_fetch_oembed()

    monkeypatch.setattr(XExtractor, "_fetch_oembed", mock_fetch)

    article = asyncio.run(x_extractor.extract("https://x.com/elonmusk/status/1234567890"))

    article = asyncio.run(x_extractor.extract("https://x.com/elonmusk/status/1234567890"))

    assert article.platform == "x"
    assert article.platform_label == "X (Twitter)"
    assert article.content_type == "social_post"
    assert article.title == "Elon Musk: Just launched Starship!"
    assert article.author == "@elonmusk"
    assert article.published_at == "March 14, 2024"
    assert "Just launched Starship!" in article.markdown
    assert "[View original post and media]" in article.markdown
    assert article.status_code == 200
    assert article.extra["tweet_url"] == "https://twitter.com/elonmusk/status/1234567890"


def test_extract_404_raises(monkeypatch):
    async def mock_fetch_404(self, url):
        raise ValueError("Tweet not found or private")

    monkeypatch.setattr(XExtractor, "_fetch_oembed", mock_fetch_404)

    with pytest.raises(ValueError, match="not found or private"):
        asyncio.run(x_extractor.extract("https://x.com/elonmusk/status/9999999999"))


def test_extract_empty_text_fallback(monkeypatch):
    """When oEmbed HTML has no <p> tag, fallback to author_name."""
    async def mock_fetch_empty(self, url):
        return {
            "author_name": "Elon Musk",
            "html": '<blockquote class="twitter-tweet">&mdash; Elon Musk (@elonmusk) <a href="https://x.com/elonmusk/status/123">Mar 1</a></blockquote>',
        }

    monkeypatch.setattr(XExtractor, "_fetch_oembed", mock_fetch_empty)

    article = asyncio.run(x_extractor.extract("https://x.com/elonmusk/status/123"))

    assert article.title == "Elon Musk: Elon Musk on X"
    assert "Elon Musk on X" in article.markdown


# ---------------------------------------------------------------------------
# Integration smoke test with real URLs (optional, skipped by default)
# ---------------------------------------------------------------------------
@pytest.mark.skip(reason="Integration test — requires network access")
def test_extract_real_x_url():
    """Run against a real X URL. Requires internet."""
    url = "https://x.com/elonmusk/status/1234567890"
    article = asyncio.run(x_extractor.extract(url))
    assert article.title
    assert article.markdown
