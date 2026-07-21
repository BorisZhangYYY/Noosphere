from __future__ import annotations

import asyncio
import os
import re
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
_MARKDOWN_IMAGE_REF_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


@dataclass
class CrawledPage:
    url: str
    success: bool
    status_code: int | None
    html: str
    cleaned_html: str
    markdown: str
    error: str | None = None
    crawler_used: str | None = None

    @property
    def fallback_used(self) -> str | None:
        """Backward compatibility: returns the same as crawler_used."""
        return self.crawler_used


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
    js_code: str | list[str] | None = None,
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
        js_code=js_code,
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
    js_code: str | list[str] | None = None,
) -> CrawledPage:
    """Call Firecrawl /scrape API as a fallback when Crawl4AI fails."""
    del excluded_tags, page_timeout, pruning_threshold, word_count_threshold, js_code  # Unused in Firecrawl path

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
                    crawler_used="firecrawl",
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
    js_code: str | list[str] | None = None,
) -> CrawledPage:
    """Crawl a URL using the configured primary crawler, falling back on failure.

    The order is determined by ``crawler.primary`` in config.json:
    - ``"crawl4ai"`` (default): try Crawl4AI first, then Firecrawl
    - ``"firecrawl"``: try Firecrawl first, then Crawl4AI

    If the fallback crawler is disabled or not configured, the primary
    result is returned even on failure.
    """
    config = load_config()
    primary = config.crawler.primary_crawler
    fallback = config.crawler.fallback_crawler

    # Map crawler names to their callables
    _crawlers: dict[str, Any] = {
        "crawl4ai": _crawl_page_crawl4ai,
        "firecrawl": _crawl_page_firecrawl,
    }

    resolved_url = _resolve_xiaoheihe_url(url)

    # Try primary crawler
    primary_fn = _crawlers.get(primary)
    if primary_fn is None:
        sys.stderr.write(f"[crawler] Unknown primary crawler '{primary}', defaulting to Crawl4AI\n")
        primary_fn = _crawl_page_crawl4ai

    primary_name = "firecrawl" if primary_fn is _crawl_page_firecrawl else "crawl4ai"

    try:
        page = await primary_fn(
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
            js_code=js_code,
        )
    except Exception as exc:
        page = CrawledPage(
            url=resolved_url,
            success=False,
            status_code=None,
            html="",
            cleaned_html="",
            markdown="",
            error=f"{primary_name}: {exc}",
        )

    weak_wechat_capture = (
        page.success
        and "mp.weixin.qq.com/s/" in resolved_url
        and len(_MARKDOWN_IMAGE_REF_RE.findall(page.markdown)) <= 1
    )
    if page.success and not weak_wechat_capture:
        page.crawler_used = primary_name
        return page

    # Primary failed — try fallback if available
    if not fallback:
        page.crawler_used = primary_name if page.success else None
        sys.stderr.write(f"[crawler] {primary_name} returned insufficient content and no fallback is configured\n" if weak_wechat_capture else f"[crawler] {primary_name} failed and no fallback configured\n")
        return page

    fallback_fn = _crawlers.get(fallback)
    if fallback_fn is None:
        sys.stderr.write(f"[crawler] {primary_name} failed and unknown fallback '{fallback}'\n")
        return page

    fallback_name = "firecrawl" if fallback_fn is _crawl_page_firecrawl else "crawl4ai"
    reason = "returned too few WeChat images" if weak_wechat_capture else "failed"
    sys.stderr.write(f"[crawler] {primary_name} {reason} for {url}, trying {fallback_name} fallback...\n")

    try:
        fallback_page = await fallback_fn(
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
            js_code=js_code,
        )
    except Exception as exc:
        fallback_page = CrawledPage(
            url=resolved_url,
            success=False,
            status_code=None,
            html="",
            cleaned_html="",
            markdown="",
            error=f"{fallback_name}: {exc}",
        )

    if fallback_page.success:
        primary_images = len(_MARKDOWN_IMAGE_REF_RE.findall(page.markdown))
        fallback_images = len(_MARKDOWN_IMAGE_REF_RE.findall(fallback_page.markdown))
        if weak_wechat_capture and (fallback_images <= primary_images or len(fallback_page.markdown) < 100):
            page.crawler_used = primary_name
            sys.stderr.write(f"[crawler] {fallback_name} did not improve the WeChat capture; keeping {primary_name}\n")
            return page
        fallback_page.crawler_used = fallback_name
        sys.stderr.write(f"[crawler] {fallback_name} fallback succeeded for {resolved_url}\n")
        return fallback_page

    sys.stderr.write(f"[crawler] {fallback_name} fallback also failed: {fallback_page.error}\n")
    if page.success:
        page.crawler_used = primary_name
        return page
    return fallback_page
