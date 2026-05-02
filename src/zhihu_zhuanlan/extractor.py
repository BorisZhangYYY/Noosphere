from __future__ import annotations

import re

from bs4 import BeautifulSoup

from src.common_func.article import Article
from src.common_func.crawler import crawl_page
from src.common_func.markdown import clean_markdown, first_text, html_to_text_markdown, meta_content


PLATFORM = "zhihu_zhuanlan"
PLATFORM_LABEL = "知乎专栏"

# Patterns that indicate Zhihu page-footer metadata (not article body)
ZHIU_NOISE_PATTERNS = (
    re.compile(r"^\s*[\d＋\+＋\d\s]+\s*人赞同了该文章"),
    re.compile(r"^\s*编辑于\s*[\d\-年月日:：\s]+$"),
    re.compile(r"^\s*作者："),
    re.compile(r"^\s*知乎号[：:]?\s*"),
    re.compile(r"^\s*关注\s*[\d，,万千\s]+"),
    re.compile(r"^\s*相关问题"),
    re.compile(r"^\s*参考来源"),
    re.compile(r"^\s*copyright", re.IGNORECASE),
)


def _is_noise_line(line: str) -> bool:
    return any(pat.match(line.strip()) for pat in ZHIU_NOISE_PATTERNS)


def _find_second_content_start(markdown: str) -> int | None:
    """Return the line index where the article body first repeats itself.

    Zhihu pages often append related-articles / author-bio sections that re-use
    content from the top of the article.  We detect this by finding the second
    occurrence of any significant content block (heading or blockquote) that
    appears after the opening metadata area.
    """
    lines = markdown.split("\n")
    n = len(lines)

    # Skip metadata block (everything before the first real content)
    content_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and stripped not in ("---",):
            content_start = i
            break

    # Build a list of (index, signature) for significant content blocks
    seen_signatures: dict[str, int] = {}  # signature -> first line index
    second_start: int | None = None

    for i in range(content_start, n):
        line = lines[i].strip()

        # Heading: any level (# to ######)
        hm = re.match(r"^(#{1,6})\s+(.+)$", line)
        if hm:
            sig = "h:" + hm.group(2).strip()
            if sig in seen_signatures and second_start is None:
                second_start = i
                break
            if sig not in seen_signatures:
                seen_signatures[sig] = i
            continue

        # Blockquote: > ...
        if line.startswith(">"):
            # Normalize: strip > and leading whitespace for signature
            bq_text = re.sub(r"^>\s*", "", line).strip()[:60]
            sig = "bq:" + bq_text
            if sig in seen_signatures and second_start is None:
                second_start = i
                break
            if sig not in seen_signatures:
                seen_signatures[sig] = i
            continue

    return second_start


def _truncate_duplicate_sections(markdown: str, title: str) -> str:
    lines = markdown.split("\n")
    second_idx = _find_second_content_start(markdown)

    if second_idx is not None and second_idx > 3:
        lines = lines[:second_idx]

    # Strip trailing noise lines
    while lines and _is_noise_line(lines[-1]):
        lines.pop()

    return "\n".join(lines).strip() + "\n"


def _strip_zd_tokens(markdown: str) -> str:
    """Remove the bulky zhihu search-token query params from URLs."""
    return re.sub(r"(\?|&)zd_token=[^&\s\"'\]\)]+", "", markdown)


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

    # P1 fixes: deduplicate trailing sections and strip noise
    markdown = _truncate_duplicate_sections(markdown, title)
    markdown = _strip_zd_tokens(markdown)

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
