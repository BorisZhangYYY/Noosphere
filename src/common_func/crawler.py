from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CRAWL4AI_RUNTIME = REPO_ROOT / ".crawl4ai-runtime"
CRAWL4AI_RUNTIME.mkdir(parents=True, exist_ok=True)
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


def _markdown_text(raw: object) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    return str(getattr(raw, "raw_markdown", "") or getattr(raw, "fit_markdown", "") or "")


async def crawl_page(
    url: str,
    *,
    css_selector: str | None = None,
    wait_for: str | None = None,
    page_timeout: int = 60000,
    delay_before_return_html: float = 0.8,
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
        content_filter=PruningContentFilter(threshold=0.45),
        content_source="cleaned_html",
    )
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        css_selector=css_selector,
        wait_for=wait_for,
        wait_until="domcontentloaded",
        page_timeout=page_timeout,
        delay_before_return_html=delay_before_return_html,
        markdown_generator=markdown_generator,
        scan_full_page=True,
        remove_overlay_elements=True,
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
