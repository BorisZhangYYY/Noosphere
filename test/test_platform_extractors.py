from __future__ import annotations

import asyncio

from src.platforms.wechat_mp import mp_extractor
from src.platforms.zhihu_zhuanlan import zhuanlan_extractor
from src.integrations.crawler import CrawledPage


def test_explicit_platform_extractor_modules_handle_known_urls():
    assert mp_extractor.handles("https://mp.weixin.qq.com/s/example")
    assert zhuanlan_extractor.handles("https://zhuanlan.zhihu.com/p/123")


def test_wechat_uses_target_elements_to_preserve_page_metadata():
    options = mp_extractor.WechatMpExtractor().crawl_options()

    assert options["target_elements"] == ["#js_content"]
    assert "css_selector" not in options


def test_wechat_extracts_metadata_outside_article_body(monkeypatch):
    body = "正文内容。" * 80
    html = f"""
    <html>
      <head><meta property="og:title" content="Meta Title"></head>
      <body>
        <h1 id="activity-name">微信文章标题</h1>
        <span id="js_name">测试公众号</span>
        <em id="publish_time">2026-05-07</em>
        <div id="js_content"><p>{body}</p></div>
      </body>
    </html>
    """

    async def fake_crawl_page(url: str, **kwargs):
        return CrawledPage(url, True, 200, html, "", body, None)

    monkeypatch.setattr("src.core.base_extractor.crawl_page", fake_crawl_page)

    article = asyncio.run(mp_extractor.extract("https://mp.weixin.qq.com/s/example"))

    assert article.title == "微信文章标题"
    assert article.author == "测试公众号"
    assert article.published_at == "2026-05-07"
