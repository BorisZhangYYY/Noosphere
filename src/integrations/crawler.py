from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import aiohttp

from src.core.config.config import load_config
from src.core.config.schema import Config
from src.core.paths.paths import get_paths

CRAWL4AI_RUNTIME = get_paths().ensure_crawl4ai_runtime_dir()
os.environ.setdefault("CRAWL4AI_BASE_DIRECTORY", str(CRAWL4AI_RUNTIME))
os.environ.setdefault("CRAWL4_AI_BASE_DIRECTORY", str(CRAWL4AI_RUNTIME))

from crawl4ai import (  # noqa: E402
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
    DefaultMarkdownGenerator,
    PruningContentFilter,
)


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class CrawledPage:
    url: str
    success: bool
    status_code: int | None
    html: str
    cleaned_html: str
    markdown: str
    error: str | None = None
    fallback_used: str | None = None


def _markdown_text(raw: object) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    return str(getattr(raw, "fit_markdown", "") or getattr(raw, "raw_markdown", "") or "")


async def _crawl_page_crawl4ai(
    url: str,
    *,
    css_selector: str | None = None,
    target_elements: list[str] | None = None,
    excluded_tags: list[str] | None = None,
    excluded_selector: str | None = None,
    wait_for: str | None = None,
    page_timeout: int = 60000,
    delay_before_return_html: float = 0.8,
    pruning_threshold: float = 0.45,
    word_count_threshold: int = 8,
) -> CrawledPage:
    browser_config = BrowserConfig(
        headless=True,
        verbose=False,
        user_agent=DEFAULT_USER_AGENT,
        enable_stealth=True,
        ignore_https_errors=True,
        viewport_width=1280,
        viewport_height=900,
    )
    markdown_generator = DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(threshold=pruning_threshold, threshold_type="fixed"),
        content_source="cleaned_html",
    )
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        word_count_threshold=word_count_threshold,
        css_selector=css_selector,
        target_elements=target_elements,
        excluded_tags=excluded_tags or ["script", "style", "noscript", "form", "nav", "footer", "header", "aside"],
        excluded_selector=excluded_selector,
        wait_for=wait_for,
        wait_until="domcontentloaded",
        page_timeout=page_timeout,
        delay_before_return_html=delay_before_return_html,
        markdown_generator=markdown_generator,
        remove_forms=True,
        scan_full_page=True,
        remove_overlay_elements=True,
        exclude_social_media_links=True,
        remove_consent_popups=True,
        magic=True,
        simulate_user=True,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=url, config=run_config)

    return CrawledPage(
        url=url,
        success=bool(getattr(result, "success", False)),
        status_code=getattr(result, "status_code", None),
        html=getattr(result, "html", "") or "",
        cleaned_html=getattr(result, "cleaned_html", "") or "",
        markdown=_markdown_text(getattr(result, "markdown", None)),
        error=getattr(result, "error_message", None),
    )


def _resolve_xiaoheihe_url(url: str) -> str:
    """Resolve Xiaoheihe share URL to its canonical link URL.

    Share URLs like /bbs/post_share?link_id=xxx redirect to /app/bbs/link/xxx.
    Firecrawl needs the canonical URL to extract content correctly.
    """
    parsed = urlparse(url)
    if "xiaoheihe.cn" not in parsed.netloc:
        return url

    query = parse_qs(parsed.query)
    link_id = query.get("link_id", [None])[0]
    if link_id:
        return f"https://www.xiaoheihe.cn/app/bbs/link/{link_id}"

    return url


def _build_firecrawl_payload(
    url: str,
    *,
    css_selector: str | None = None,
    target_elements: list[str] | None = None,
    excluded_selector: str | None = None,
    wait_for: str | None = None,
    delay_before_return_html: float = 5.0,
) -> dict[str, Any]:
    """Map Crawl4AI options to Firecrawl /scrape payload.

    Note: we intentionally do NOT map css_selector/target_elements to
    Firecrawl includeTags, nor excluded_selector to excludeTags.
    Firecrawl's onlyMainContent already extracts the main article body.
    Passing narrow CSS selectors can cause Firecrawl to return empty
    content when the selector does not match its rendered DOM.
    """
    del css_selector, target_elements, excluded_selector
    payload: dict[str, Any] = {
        "url": url,
        "formats": ["markdown"],
        "onlyMainContent": True,
    }

    if wait_for or delay_before_return_html:
        # Most JS-heavy pages need at least 5s; cap at 15s for Firecrawl API limits.
        payload["waitFor"] = min(max(int(delay_before_return_html * 1000), 5000), 15000)

    return payload


async def _crawl_page_firecrawl(
    url: str,
    *,
    css_selector: str | None = None,
    target_elements: list[str] | None = None,
    excluded_tags: list[str] | None = None,
    excluded_selector: str | None = None,
    wait_for: str | None = None,
    page_timeout: int = 60000,
    delay_before_return_html: float = 0.8,
    pruning_threshold: float = 0.45,
    word_count_threshold: int = 8,
) -> CrawledPage:
    """Call Firecrawl /scrape API as a fallback when Crawl4AI fails."""
    del excluded_tags, page_timeout, pruning_threshold, word_count_threshold  # Unused in Firecrawl path

    config = load_config()
    api_key = config.crawler.firecrawl.api_key or ""
    api_base = config.crawler.firecrawl.api_base
    proxy = config.proxy.https or config.proxy.http if config.proxy else None

    payload = _build_firecrawl_payload(
        url,
        css_selector=css_selector,
        target_elements=target_elements,
        excluded_selector=excluded_selector,
        wait_for=wait_for,
        delay_before_return_html=delay_before_return_html,
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
            async with session.post(
                f"{api_base}/scrape",
                headers=headers,
                json=payload,
                proxy=proxy,
            ) as response:
                response.raise_for_status()
                data = await response.json()

                if not data.get("success"):
                    error = data.get("error") or data.get("message") or "Firecrawl scrape failed"
                    return CrawledPage(
                        url=url,
                        success=False,
                        status_code=response.status,
                        html="",
                        cleaned_html="",
                        markdown="",
                        error=f"Firecrawl: {error}",
                    )

                scrape_data = data.get("data", {})
                metadata = scrape_data.get("metadata", {})
                markdown = scrape_data.get("markdown", "") or ""

                return CrawledPage(
                    url=metadata.get("url") or url,
                    success=True,
                    status_code=metadata.get("statusCode") or 200,
                    html="",
                    cleaned_html="",
                    markdown=markdown,
                    error=None,
                    fallback_used="firecrawl",
                )

    except asyncio.TimeoutError:
        return CrawledPage(
            url=url,
            success=False,
            status_code=None,
            html="",
            cleaned_html="",
            markdown="",
            error="Firecrawl: request timeout",
        )
    except aiohttp.ClientError as exc:
        return CrawledPage(
            url=url,
            success=False,
            status_code=None,
            html="",
            cleaned_html="",
            markdown="",
            error=f"Firecrawl: client error {exc}",
        )
    except Exception as exc:
        return CrawledPage(
            url=url,
            success=False,
            status_code=None,
            html="",
            cleaned_html="",
            markdown="",
            error=f"Firecrawl: unexpected error {exc}",
        )


async def crawl_page(
    url: str,
    *,
    css_selector: str | None = None,
    target_elements: list[str] | None = None,
    excluded_tags: list[str] | None = None,
    excluded_selector: str | None = None,
    wait_for: str | None = None,
    page_timeout: int = 60000,
    delay_before_return_html: float = 0.8,
    pruning_threshold: float = 0.45,
    word_count_threshold: int = 8,
) -> CrawledPage:
    """Try Crawl4AI first, fall back to Firecrawl on failure."""
    try:
        page = await _crawl_page_crawl4ai(
            url,
            css_selector=css_selector,
            target_elements=target_elements,
            excluded_tags=excluded_tags,
            excluded_selector=excluded_selector,
            wait_for=wait_for,
            page_timeout=page_timeout,
            delay_before_return_html=delay_before_return_html,
            pruning_threshold=pruning_threshold,
            word_count_threshold=word_count_threshold,
        )
    except Exception as exc:
        page = CrawledPage(
            url=url,
            success=False,
            status_code=None,
            html="",
            cleaned_html="",
            markdown="",
            error=f"Crawl4AI: {exc}",
        )

    if page.success:
        return page

    config = load_config()
    if not config.crawler.firecrawl_enabled:
        return page

    resolved_url = _resolve_xiaoheihe_url(url)
    sys.stderr.write(f"[crawler] Crawl4AI failed for {url}, trying Firecrawl fallback...\n")

    firecrawl_page = await _crawl_page_firecrawl(
        resolved_url,
        css_selector=css_selector,
        target_elements=target_elements,
        excluded_tags=excluded_tags,
        excluded_selector=excluded_selector,
        wait_for=wait_for,
        page_timeout=page_timeout,
        delay_before_return_html=delay_before_return_html,
        pruning_threshold=pruning_threshold,
        word_count_threshold=word_count_threshold,
    )
    if firecrawl_page.success:
        sys.stderr.write(f"[crawler] Firecrawl fallback succeeded for {resolved_url}\n")
        return firecrawl_page

    sys.stderr.write(f"[crawler] Firecrawl fallback also failed: {firecrawl_page.error}\n")
    return firecrawl_page
