from __future__ import annotations

import asyncio

import pytest
from bs4 import BeautifulSoup, Tag

from src.core.base_extractor import BaseArticleExtractor
from src.integrations.crawler import CrawledPage


class DummyExtractor(BaseArticleExtractor):
    platform = "dummy"
    platform_label = "Dummy"
    fallback_title = "Fallback Title"

    def handles(self, url: str) -> bool:
        return "example.com" in url

    def crawl_options(self) -> dict[str, object]:
        return {"css_selector": "article"}

    def extract_title(self, soup: BeautifulSoup) -> str | None:
        node = soup.select_one("h1")
        return node.get_text(" ", strip=True) if node else None

    def extract_author(self, soup: BeautifulSoup) -> str | None:
        node = soup.select_one(".author")
        return node.get_text(" ", strip=True) if node else None

    def extract_published_at(self, soup: BeautifulSoup) -> str | None:
        node = soup.select_one("time")
        return node.get_text(" ", strip=True) if node else None

    def content_node(self, soup: BeautifulSoup) -> Tag | None:
        return soup.select_one("article")

    def clean_body(self, markdown: str, title: str) -> str:
        return markdown.replace("NOISE", "").strip()


def test_base_extractor_falls_back_to_html_content(monkeypatch):
    captured = {}
    body = "Clean body paragraph. " * 8 + "NOISE"

    async def fake_crawl_page(url: str, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        html = f"""
        <html>
          <body>
            <h1>Article Title</h1>
            <span class="author">Ada</span>
            <time>2026-05-07</time>
            <article><p>{body}</p></article>
          </body>
        </html>
        """
        return CrawledPage(url, True, 200, html, "", "short", None)

    monkeypatch.setattr("src.core.base_extractor.crawl_page", fake_crawl_page)

    article = asyncio.run(DummyExtractor().extract("https://example.com/article"))

    assert captured == {
        "url": "https://example.com/article",
        "kwargs": {"css_selector": "article"},
    }
    assert article.platform == "dummy"
    assert article.title == "Article Title"
    assert article.author == "Ada"
    assert article.published_at == "2026-05-07"
    assert "Clean body paragraph." in article.markdown
    assert "NOISE" not in article.markdown
    assert article.extra == {"crawl_success": True, "crawl_error": None}


def test_base_extractor_validates_after_platform_cleaning(monkeypatch):
    class EmptyAfterCleanExtractor(DummyExtractor):
        def clean_body(self, markdown: str, title: str) -> str:
            return ""

    async def fake_crawl_page(url: str, **kwargs):
        return CrawledPage(url, True, 200, "", "", "Long body. " * 20, "boom")

    monkeypatch.setattr("src.core.base_extractor.crawl_page", fake_crawl_page)

    with pytest.raises(ValueError, match="Dummy article body is too short"):
        asyncio.run(EmptyAfterCleanExtractor().extract("https://example.com/article"))
