from src.integrations.crawler import _build_firecrawl_payload


def test_firecrawl_omits_wait_for_for_wechat_articles() -> None:
    payload = _build_firecrawl_payload("https://mp.weixin.qq.com/s/example")

    assert "waitFor" not in payload


def test_firecrawl_keeps_wait_for_for_dynamic_pages() -> None:
    payload = _build_firecrawl_payload("https://example.com/article")

    assert payload["waitFor"] == 5000
