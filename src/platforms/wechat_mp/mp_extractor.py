from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from src.core.article import Article
from src.core.base_extractor import BaseArticleExtractor
from src.core.markdown import first_text, meta_content
from src.integrations.crawler import CrawledPage

PLATFORM = "wechat_mp"
PLATFORM_LABEL = "微信公众号"
FALLBACK_TITLE = "微信公众号文章"


class WechatMpExtractor(BaseArticleExtractor):
    platform = PLATFORM
    platform_label = PLATFORM_LABEL
    fallback_title = FALLBACK_TITLE

    def handles(self, url: str) -> bool:
        return "mp.weixin.qq.com/s/" in url

    def crawl_options(self) -> dict[str, object]:
        return {
            "target_elements": ["#js_content"],
            "wait_for": "css:#js_content",
            "page_timeout": 60000,
            "delay_before_return_html": 1.2,
            "pruning_threshold": 0.42,
            "word_count_threshold": 5,
        }

    def extract_title(self, soup: BeautifulSoup) -> str | None:
        return first_text(soup, ["#activity-name", "h1", "title"]) or meta_content(
            soup,
            ['meta[property="og:title"]'],
        )

    def extract_author(self, soup: BeautifulSoup) -> str | None:
        return first_text(soup, ["#js_name", "#profileBt a", ".account_nickname_inner"])

    def extract_published_at(self, soup: BeautifulSoup) -> str | None:
        return first_text(soup, ["#publish_time", "em#publish_time"])

    def content_node(self, soup: BeautifulSoup) -> Tag | None:
        return soup.select_one("#js_content")

    def too_short_message(self, page: CrawledPage) -> str:
        return f"WeChat article body is too short; crawl error={page.error!r}"


extractor = WechatMpExtractor()


def handles(url: str) -> bool:
    return extractor.handles(url)


async def extract(url: str) -> Article:
    return await extractor.extract(url)
