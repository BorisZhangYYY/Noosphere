from __future__ import annotations

import asyncio

from src.platforms.wechat_mp import mp_extractor
from src.platforms.xiaoheihe import heihe_extractor
from src.platforms.zhihu_zhuanlan import zhuanlan_extractor
from src.integrations.crawler import CrawledPage


def test_explicit_platform_extractor_modules_handle_known_urls():
    assert mp_extractor.handles("https://mp.weixin.qq.com/s/example")
    assert heihe_extractor.handles("https://www.xiaoheihe.cn/bbs/post_share?link_id=abc")
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


def test_xiaoheihe_extracts_main_post_without_comments_or_tags(monkeypatch):
    body = "星际拓荒里有一个地方，我后来很少回去。" * 20
    html = f"""
    <html>
      <head><title>接力 - 小黑盒</title></head>
      <body>
        <div class="hb-bbs-image-text">
          <div class="image-text__header-image">
            <img src="https://example.com/header.webp">
          </div>
          <div class="image-text__container">
            <div class="link-section-user">
              <a class="link-user__user-wrapper">BlossomNight23333</a>
              <button class="link-user__follow-btn">关注</button>
            </div>
            <div class="link-section-title"><div class="section-title__content">接力</div></div>
            <div class="image-text__content"><p>{body}</p></div>
            <div class="link-section-tags">Steam 星际拓荒</div>
            <div class="link-section-link-data"><div class="link-data__time">2026-04-18</div></div>
          </div>
        </div>
        <div class="comment-list">这是一条评论</div>
      </body>
    </html>
    """

    async def fake_crawl_page(url: str, **kwargs):
        return CrawledPage(url, True, 302, html, "", "", None)

    monkeypatch.setattr("src.platforms.xiaoheihe.heihe_extractor.crawl_page", fake_crawl_page)

    article = asyncio.run(heihe_extractor.extract("https://www.xiaoheihe.cn/bbs/post_share?link_id=abc"))

    assert article.platform == "xiaoheihe"
    assert article.platform_label == "小黑盒"
    assert article.title == "接力"
    assert article.author == "BlossomNight23333"
    assert article.published_at == "2026-04-18"
    assert "![Image](https://example.com/header.webp)" in article.markdown
    assert "星际拓荒里有一个地方" in article.markdown
    assert "这是一条评论" not in article.markdown
    assert "Steam 星际拓荒" not in article.markdown
