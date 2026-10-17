"""Reject access pages before spending review tokens or saving fake articles."""
from types import SimpleNamespace

import pytest

from src.core.extraction_quality import zhihu_access_page
from src.integrations.crawler import CrawledPage, crawl_page
from src.platforms.zhihu_zhuanlan.zhuanlan_extractor import ZhihuZhuanlanExtractor

URL = "https://zhuanlan.zhihu.com/p/640641794"
LOGIN = "![ZhiHu logo](https://example.test/logo.png)\n\n[知乎](https://www.zhihu.com/)\n\n请您登录后查看更多专业优质内容。\n\n_想来知乎工作？请发送邮件到 jobs@zhihu.com_\n"
ARTICLE = "# Actual article\n\n" + "A complete substantive paragraph about attention and memory.\n\n" * 40


def page(markdown, status=200):
    return CrawledPage(url=URL, success=True, status_code=status, html="", cleaned_html="", markdown=markdown)


@pytest.mark.parametrize("markdown,status", [(LOGIN, 200), ("安全验证", 200), ("Access denied", 403), ("Rate limit", 429)])
@pytest.mark.asyncio
async def test_zhihu_access_pages_are_not_articles(markdown, status):
    with pytest.raises(ValueError, match="did not return article content"):
        await ZhihuZhuanlanExtractor()._parse(page(markdown, status), URL)


@pytest.mark.asyncio
async def test_full_article_can_quote_an_access_message_without_being_rejected():
    markdown = ARTICLE + "\n请您登录后查看更多专业优质内容。\n"
    assert not zhihu_access_page(markdown)
    article = await ZhihuZhuanlanExtractor()._parse(page(markdown), URL)
    assert "complete substantive paragraph" in article.markdown


@pytest.mark.asyncio
@pytest.mark.parametrize("fallback_body", [ARTICLE, LOGIN])
async def test_login_page_tries_fallback_and_never_silently_accepts_another_login_page(monkeypatch, fallback_body):
    config = SimpleNamespace(crawler=SimpleNamespace(primary_crawler="firecrawl", fallback_crawler="crawl4ai"))
    calls = []

    async def primary(url, **kwargs):
        calls.append("primary")
        return page(LOGIN)

    async def fallback(url, **kwargs):
        calls.append("fallback")
        return page(fallback_body)

    monkeypatch.setattr("src.integrations.crawler.load_config", lambda: config)
    monkeypatch.setattr("src.integrations.crawler._crawl_page_firecrawl", primary)
    monkeypatch.setattr("src.integrations.crawler._crawl_page_crawl4ai", fallback)
    result = await crawl_page(URL)
    assert calls == ["primary", "fallback"]
    if fallback_body == ARTICLE:
        assert result.crawler_used == "crawl4ai"
        assert (await ZhihuZhuanlanExtractor()._parse(result, URL)).title == "Actual article"
    else:
        with pytest.raises(ValueError, match="did not return article content"):
            await ZhihuZhuanlanExtractor()._parse(result, URL)


@pytest.mark.asyncio
async def test_capture_of_login_page_fails_before_any_ai_review(monkeypatch):
    from src.api.web import _capture_jobs, _run_capture_job
    invoked = []

    async def extract(url):
        await ZhihuZhuanlanExtractor()._parse(page(LOGIN), url)
        raise AssertionError("Access page must not produce an article workspace")

    async def review(*args, **kwargs):
        invoked.append(True)
        raise AssertionError("AI must not receive an access page")

    monkeypatch.setattr("src.graph.graph.run_extract_graph", extract)
    monkeypatch.setattr("src.graph.graph.run_ai_review_graph", review)
    job_id = "invalid-content-regression"
    _capture_jobs[job_id] = {"id": job_id, "events": [], "reviewPreview": ""}
    try:
        await _run_capture_job(job_id, URL, "ai_then_manual", "original", "source")
        assert _capture_jobs[job_id]["status"] == "failed"
        assert "did not return article content" in _capture_jobs[job_id]["error"]
        assert not _capture_jobs[job_id].get("articleId")
        assert not invoked
    finally:
        _capture_jobs.pop(job_id, None)
