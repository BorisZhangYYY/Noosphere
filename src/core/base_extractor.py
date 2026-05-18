from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from bs4 import BeautifulSoup, Tag

from src.core.article import Article
from src.core.markdown import clean_markdown, html_to_text_markdown
from src.integrations.crawler import CrawledPage, crawl_page


class BaseArticleExtractor(ABC):
    platform: str
    platform_label: str
    fallback_title: str
    content_type: str = "article"
    body_min_length = 100

    @abstractmethod
    def handles(self, url: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def crawl_options(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def extract_title(self, soup: BeautifulSoup) -> str | None:
        raise NotImplementedError

    def extract_author(self, soup: BeautifulSoup) -> str | None:
        return None

    def extract_published_at(self, soup: BeautifulSoup) -> str | None:
        return None

    @abstractmethod
    def content_node(self, soup: BeautifulSoup) -> Tag | None:
        raise NotImplementedError

    def clean_body(self, markdown: str, title: str) -> str:
        return markdown

    async def extract(self, url: str) -> Article:
        page = await crawl_page(url, **self.crawl_options())
        soup = BeautifulSoup(page.html or page.cleaned_html, "lxml")
        title = self.extract_title(soup) or self.fallback_title

        markdown = clean_markdown(page.markdown)
        if len(markdown) < self.body_min_length:
            markdown = html_to_text_markdown(self.content_node(soup))
        markdown = self.clean_body(markdown, title)

        if len(markdown) < self.body_min_length:
            raise ValueError(self.too_short_message(page))

        return Article(
            platform=self.platform,
            platform_label=self.platform_label,
            content_type=self.content_type,
            url=url,
            title=title,
            author=self.extract_author(soup),
            published_at=self.extract_published_at(soup),
            markdown=markdown,
            status_code=page.status_code,
            extra={"crawl_success": page.success, "crawl_error": page.error},
        )

    def too_short_message(self, page: CrawledPage) -> str:
        return (
            f"{self.platform_label} article body is too short; "
            f"status={page.status_code}, crawl error={page.error!r}"
        )
