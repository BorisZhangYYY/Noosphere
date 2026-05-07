from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from src.core.article import Article
from src.core.base_extractor import BaseArticleExtractor
from src.core.markdown import first_text, meta_content
from src.integrations.crawler import CrawledPage
from src.platforms.zhihu_zhuanlan.cleaning import clean


PLATFORM = "zhihu_zhuanlan"
PLATFORM_LABEL = "知乎专栏"
FALLBACK_TITLE = "知乎专栏文章"


class ZhihuZhuanlanExtractor(BaseArticleExtractor):
    platform = PLATFORM
    platform_label = PLATFORM_LABEL
    fallback_title = FALLBACK_TITLE

    def handles(self, url: str) -> bool:
        return "zhuanlan.zhihu.com/p/" in url

    def crawl_options(self) -> dict[str, object]:
        return {
            "css_selector": ".Post-RichTextContainer, .RichContent-inner, .RichText, article",
            "excluded_selector": (
                ".Comments-container, .Recommendations-Main, .ContentItem-actions, "
                ".Reward, .Post-SideActions"
            ),
            "wait_for": None,
            "page_timeout": 60000,
            "delay_before_return_html": 1.0,
            "pruning_threshold": 0.48,
            "word_count_threshold": 5,
        }

    def extract_title(self, soup: BeautifulSoup) -> str | None:
        return first_text(soup, ["h1.Post-Title", ".Post-Title", "h1", "title"]) or meta_content(
            soup,
            ['meta[property="og:title"]', 'meta[name="title"]'],
        )

    def extract_author(self, soup: BeautifulSoup) -> str | None:
        return first_text(soup, [".AuthorInfo-name", ".UserLink-link", ".Post-Author .name"]) or meta_content(
            soup,
            ['meta[name="author"]'],
        )

    def extract_published_at(self, soup: BeautifulSoup) -> str | None:
        return meta_content(
            soup,
            [
                'meta[property="article:published_time"]',
                'meta[itemprop="datePublished"]',
                'meta[name="publishdate"]',
            ],
        )

    def content_node(self, soup: BeautifulSoup) -> Tag | None:
        return soup.select_one(".Post-RichTextContainer, .RichContent-inner, .RichText, article")

    def clean_body(self, markdown: str, title: str) -> str:
        return clean(markdown, title)

    def too_short_message(self, page: CrawledPage) -> str:
        return f"Zhihu article body is too short; status={page.status_code}, crawl error={page.error!r}"


extractor = ZhihuZhuanlanExtractor()


def handles(url: str) -> bool:
    return extractor.handles(url)


async def extract(url: str) -> Article:
    return await extractor.extract(url)
