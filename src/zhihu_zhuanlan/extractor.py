from __future__ import annotations

from bs4 import BeautifulSoup

from src.common_func.article import Article
from src.common_func.crawler import crawl_page
from src.common_func.markdown import clean_markdown, first_text, html_to_text_markdown, meta_content


PLATFORM = "zhihu_zhuanlan"
PLATFORM_LABEL = "知乎专栏"


def handles(url: str) -> bool:
    return "zhuanlan.zhihu.com/p/" in url


async def extract(url: str) -> Article:
    page = await crawl_page(
        url,
        css_selector=".Post-RichTextContainer, .RichContent-inner, .RichText, article",
        wait_for=None,
        page_timeout=60000,
        delay_before_return_html=1.0,
    )
    soup = BeautifulSoup(page.html or page.cleaned_html, "lxml")

    title = (
        first_text(soup, ["h1.Post-Title", ".Post-Title", "h1", "title"])
        or meta_content(soup, ['meta[property="og:title"]', 'meta[name="title"]'])
        or "知乎专栏文章"
    )
    author = (
        first_text(soup, [".AuthorInfo-name", ".UserLink-link", ".Post-Author .name"])
        or meta_content(soup, ['meta[name="author"]'])
    )
    published_at = meta_content(
        soup,
        [
            'meta[property="article:published_time"]',
            'meta[itemprop="datePublished"]',
            'meta[name="publishdate"]',
        ],
    )

    content_node = soup.select_one(".Post-RichTextContainer, .RichContent-inner, .RichText, article")
    markdown = clean_markdown(page.markdown)
    if len(markdown) < 100:
        markdown = html_to_text_markdown(content_node)

    if len(markdown) < 100:
        raise ValueError(f"Zhihu article body is too short; status={page.status_code}, crawl error={page.error!r}")

    return Article(
        platform=PLATFORM,
        platform_label=PLATFORM_LABEL,
        url=url,
        title=title,
        author=author,
        published_at=published_at,
        markdown=markdown,
        status_code=page.status_code,
        extra={"crawl_success": page.success, "crawl_error": page.error},
    )
