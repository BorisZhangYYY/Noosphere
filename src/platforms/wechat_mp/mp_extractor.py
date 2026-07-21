from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from src.core.models.article import Article
from src.core.base_extractor import BaseArticleExtractor
from src.core.registry import register_extractor
from src.core.markdown.cleaner import first_text, meta_content
from src.integrations.crawler import CrawledPage

import re

PLATFORM = "wechat_mp"
PLATFORM_LABEL = "微信公众号"
FALLBACK_TITLE = "微信公众号文章"

# Heading that contains only an image (no text)
_HEADING_IMAGE_ONLY_RE = re.compile(r"^#{1,3}\s*!\[.*?\]\([^)]+\)\s*$")

# Short heading that looks like a publisher/source label (<=15 chars, no long text)
_SHORT_HEADING_RE = re.compile(r"^#{1,3}\s*(?:\*\*)?[^*#\n]{1,15}(?:\*\*)?\s*$")


@register_extractor("wechat_mp", url_patterns=["mp.weixin.qq.com/s/"])
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
            # WeChat keeps most article images in data-src until they enter the
            # viewport. Normalise those attributes before Crawl4AI generates
            # Markdown so the asset stage can localise every content image.
            "js_code": """
                document.querySelectorAll('#js_content img').forEach((image) => {
                  const source = image.getAttribute('data-src') || image.getAttribute('data-original');
                  if (source && (source.startsWith('https://') || source.startsWith('http://'))) image.setAttribute('src', source);
                });
            """,
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

    def clean_body(self, markdown: str, title: str) -> str:
        """Remove the platform banner image that duplicates the cover image.

        WeChat MP articles often place the same cover image twice:
        1. As the actual article cover (outside the body)
        2. As a platform banner in a heading before the publisher name
           (e.g. ``### ![](banner.jpg)`` followed by ``### **新智元报道**``)

        This method detects the pattern generically: a heading containing
        only an image followed by a short heading (publisher label).
        """
        lines = markdown.split("\n")
        result: list[str] = []
        i = 0
        while i < len(lines):
            heading_img = _HEADING_IMAGE_ONLY_RE.match(lines[i])
            if heading_img:
                # Look ahead for a short publisher/source heading
                found_publisher = False
                for j in range(i + 1, min(i + 6, len(lines))):
                    next_line = lines[j].strip()
                    if not next_line:
                        continue
                    if _SHORT_HEADING_RE.match(next_line):
                        found_publisher = True
                        break
                    # Stop scanning if we hit a non-empty, non-heading line
                    if not next_line.startswith("#"):
                        break
                if found_publisher:
                    # Skip this banner image line so it is never downloaded
                    i += 1
                    continue
            result.append(lines[i])
            i += 1
        return "\n".join(result)
