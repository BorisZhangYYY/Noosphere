from src.platforms.wechat_mp.mp_extractor import (
    WechatMpExtractor,
    _author_from_markdown,
    _published_from_markdown,
)


def test_wechat_metadata_falls_back_to_firecrawl_markdown() -> None:
    markdown = """Original吕倩吕倩
第一财经

_2026年7月22日 00:13_

****作者 \\|**** 第一财经 吕倩
"""

    assert _author_from_markdown(markdown) == "第一财经 吕倩"
    assert _published_from_markdown(markdown) == "2026年7月22日 00:13"


def test_wechat_clean_body_removes_reader_chrome_and_trailing_dialog() -> None:
    markdown = """Original吕倩吕倩
在小说阅读器读本章
去阅读
在小说阅读器中沉浸阅读

正文第一段。

正文第二段。

**·联系我们**

**推荐阅读**

Send Message

写留言:

## 确认提交投诉
你可以补充投诉原因（选填）
"""

    cleaned = WechatMpExtractor().clean_body(markdown, "标题")

    assert "正文第一段" in cleaned
    assert "小说阅读器" not in cleaned
    assert "Original" not in cleaned
    assert "联系我们" not in cleaned
    assert "推荐阅读" not in cleaned
    assert "Send Message" not in cleaned
    assert "确认提交投诉" not in cleaned
