from __future__ import annotations

import json
import urllib.parse

from bs4 import BeautifulSoup, Tag

from src.core.models.article import Article
from src.core.base_extractor import BaseArticleExtractor
from src.core.registry import register_extractor
from src.core.markdown.cleaner import clean_markdown, extract_title_from_markdown, first_text, html_to_text_markdown, meta_content
from src.integrations.crawler import CrawledPage, crawl_page

PLATFORM = "xiaoheihe"
PLATFORM_LABEL = "小黑盒"
FALLBACK_TITLE = "小黑盒帖子"


@register_extractor(
    "xiaoheihe",
    url_patterns=[
        "xiaoheihe.cn/bbs/post_share",
        "xiaoheihe.cn/app/bbs/link/",
        "api.xiaoheihe.cn/v3/bbs/app/api/web/share",
    ],
)
class XiaoheiheExtractor(BaseArticleExtractor):
    platform = PLATFORM
    platform_label = PLATFORM_LABEL
    fallback_title = FALLBACK_TITLE

    def handles(self, url: str) -> bool:
        return any(
            pattern in url
            for pattern in (
                "xiaoheihe.cn/bbs/post_share",
                "xiaoheihe.cn/app/bbs/link/",
                "api.xiaoheihe.cn/v3/bbs/app/api/web/share",
            )
        )

    def crawl_options(self) -> dict[str, object]:
        return {
            "css_selector": ".hb-bbs-image-text",
            "wait_for": "css:.hb-bbs-image-text",
            "page_timeout": 60000,
            "delay_before_return_html": 2.0,
            "pruning_threshold": 0.35,
            "word_count_threshold": 3,
        }

    def extract_title(self, soup: BeautifulSoup) -> str | None:
        title = first_text(
            soup,
            [".link-section-title .section-title__content", ".link-section-title", "h1", "title"],
        ) or meta_content(soup, ['meta[property="og:title"]', 'meta[name="title"]'])
        return clean_title(title)

    def extract_author(self, soup: BeautifulSoup) -> str | None:
        return first_text(soup, [".link-user__user-wrapper", ".link-section-user a"])

    def extract_published_at(self, soup: BeautifulSoup) -> str | None:
        return first_text(soup, [".link-data__time"])

    def content_node(self, soup: BeautifulSoup) -> Tag | None:
        return soup.select_one(".image-text__content")

    async def extract(self, url: str) -> Article:
        page = await crawl_page(url, **self.crawl_options())
        soup = BeautifulSoup(page.html or page.cleaned_html, "lxml")
        title = (
            self.extract_title(soup)
            or extract_title_from_markdown(page.markdown)
            or title_from_redirect_data(url)
            or self.fallback_title
        )
        if page.fallback_used == "firecrawl" and len(page.markdown) >= self.body_min_length:
            markdown = page.markdown
        else:
            markdown = extract_post_markdown(soup)
            if len(markdown) < self.body_min_length:
                # Fallback to Crawl4AI-generated markdown when HTML parsing yields nothing.
                markdown = page.markdown
            if len(markdown) < self.body_min_length:
                markdown = description_from_redirect_data(url)
        markdown = self.clean_body(clean_markdown(markdown), title)
        if len(markdown) < self.body_min_length:
            raise ValueError(self.too_short_message(page))

        return Article(
            platform=self.platform,
            platform_label=self.platform_label,
            url=url,
            title=title,
            author=self.extract_author(soup),
            published_at=self.extract_published_at(soup),
            markdown=markdown,
            status_code=page.status_code,
            extra={
                "crawl_success": page.success,
                "crawl_error": page.error,
                "fallback_used": page.fallback_used,
            },
        )

    def too_short_message(self, page: CrawledPage) -> str:
        return f"Xiaoheihe post body is too short; status={page.status_code}, crawl error={page.error!r}"


def extract_post_markdown(soup: BeautifulSoup) -> str:
    parts: list[str] = []
    root = soup.select_one(".hb-bbs-image-text")
    if not root:
        return ""

    header = root.select_one(".image-text__header-image")
    if header:
        parts.extend(image_markdown(header))

    content = root.select_one(".image-text__content")
    if content:
        body = html_to_text_markdown(content).strip()
        if body:
            parts.append(body)

    return "\n\n".join(parts).strip()


def image_markdown(node: Tag) -> list[str]:
    lines: list[str] = []
    for image in node.select("img"):
        src = str(image.get("src") or image.get("data-src") or "").strip()
        if not src:
            continue
        alt = str(image.get("alt") or "Image").strip() or "Image"
        lines.append(f"![{alt}]({src})")
    return lines


def title_from_redirect_data(url: str) -> str:
    data = redirect_link_data(url)
    return clean_title(str(data.get("title") or "").strip())


def description_from_redirect_data(url: str) -> str:
    data = redirect_link_data(url)
    return str(data.get("description") or "").strip()


def redirect_link_data(url: str) -> dict[str, object]:
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    raw = (query.get("redirect_data") or [""])[0]
    if not raw:
        return {}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    link = data.get("link") if isinstance(data, dict) else {}
    return link if isinstance(link, dict) else {}


def clean_title(title: str | None) -> str:
    cleaned = str(title or "").strip()
    # Xiaoheihe appends " - 小黑盒" to article titles; remove it.
    return cleaned.removesuffix(" - 小黑盒").strip()
