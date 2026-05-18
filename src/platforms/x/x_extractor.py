from __future__ import annotations

import re
from urllib.parse import quote, urlparse

import aiohttp
from bs4 import BeautifulSoup

from src.core.article import Article
from src.core.base_extractor import BaseArticleExtractor

PLATFORM = "x"
PLATFORM_LABEL = "X (Twitter)"
FALLBACK_TITLE = "X Post"
OEMBED_ENDPOINT = "https://publish.twitter.com/oembed"


class XExtractor(BaseArticleExtractor):
    platform = PLATFORM
    platform_label = PLATFORM_LABEL
    fallback_title = FALLBACK_TITLE
    content_type = "social_post"
    body_min_length = 10

    def handles(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return host in ("x.com", "www.x.com", "twitter.com", "www.twitter.com")

    def _extract_tweet_id(self, url: str) -> str:
        match = re.search(r"/status/(\d+)(?:\?|$)", url)
        if not match:
            raise ValueError(f"Invalid X URL: no tweet ID found in {url}")
        return match.group(1)

    async def _fetch_oembed(self, url: str) -> dict:
        params = f"?url={quote(url, safe='')}&omit_script=true&dnt=true"
        async with aiohttp.ClientSession() as session:
            async with session.get(OEMBED_ENDPOINT + params, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status == 404:
                    raise ValueError(f"Tweet not found or private: {url}")
                response.raise_for_status()
                return await response.json()

    def _parse_oembed_html(self, html: str) -> dict:
        soup = BeautifulSoup(html, "lxml")
        blockquote = soup.find("blockquote")
        if not blockquote:
            raise ValueError("oEmbed response missing blockquote")

        p_tag = blockquote.find("p")
        text = self._html_to_markdown(str(p_tag)) if p_tag else ""

        author_name = ""
        author_handle = ""
        published_at = ""
        tweet_url = ""

        last_a = blockquote.find_all("a")[-1] if blockquote.find_all("a") else None
        if last_a:
            published_at = last_a.get_text(strip=True)
            tweet_url = last_a.get("href", "")

        # Extract author from &mdash; text node
        mdash_text = ""
        for elem in blockquote.children:
            if isinstance(elem, str) and ("—" in elem or "&mdash;" in elem):
                mdash_text = str(elem)
                break

        if not mdash_text:
            full_text = blockquote.get_text(" ", strip=True)
            if "—" in full_text:
                mdash_text = full_text.split("—")[-1]

        if mdash_text:
            author_match = re.search(r"—\s*(.+?)\s*\(@([^)]+)\)", mdash_text)
            if not author_match:
                author_match = re.search(r"—\s*(.+?)\s*\(@([^)]+)\)", blockquote.get_text(" ", strip=True))
            if author_match:
                author_name = author_match.group(1).strip()
                author_handle = author_match.group(2).strip()

        return {
            "text": text,
            "author_name": author_name,
            "author_handle": author_handle,
            "published_at": published_at,
            "tweet_url": tweet_url or "",
        }

    def crawl_options(self) -> dict[str, object]:
        return {}

    def extract_title(self, soup: BeautifulSoup) -> str | None:
        return None

    def content_node(self, soup: BeautifulSoup) -> Tag | None:
        return None

    def _html_to_markdown(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a"):
            href = a.get("href", "")
            text = a.get_text(strip=True)
            a.replace_with(f"[{text}]({href})")
        for br in soup.find_all("br"):
            br.replace_with("\n")
        text = soup.get_text("", strip=True)
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    def _synthesize_title(self, author_name: str, text: str) -> str:
        preview = text[:60].replace("\n", " ")
        if len(text) > 60:
            preview = preview.rstrip() + "..."
        author = author_name or self.fallback_title
        return f"{author}: {preview}"

    async def extract(self, url: str) -> Article:
        self._extract_tweet_id(url)
        oembed_data = await self._fetch_oembed(url)
        parsed = self._parse_oembed_html(oembed_data.get("html", ""))

        text = parsed["text"]
        if not text:
            text = oembed_data.get("author_name", "") + " on X"

        title = self._synthesize_title(parsed["author_name"], text)
        markdown = f"{text}\n\n[View original post and media]({url})"

        return Article(
            platform=self.platform,
            platform_label=self.platform_label,
            content_type=self.content_type,
            url=url,
            title=title,
            author=f"@{parsed['author_handle']}" if parsed["author_handle"] else None,
            published_at=parsed["published_at"] or None,
            markdown=markdown,
            status_code=200,
            extra={"tweet_url": parsed["tweet_url"] or url},
        )


extractor = XExtractor()


def handles(url: str) -> bool:
    return extractor.handles(url)


async def extract(url: str) -> Article:
    return await extractor.extract(url)
