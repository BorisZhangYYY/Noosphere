from __future__ import annotations

from src.platforms.wechat_mp.cleaning import trim_footer
from src.platforms.zhihu_zhuanlan.cleaning import clean, strip_zd_tokens


def test_wechat_cleaning_trims_known_footer_marker():
    markdown = "正文第一段\n\n继续滑动看下一个\n\n无关内容"

    assert trim_footer(markdown) == "正文第一段"


def test_zhihu_cleaning_strips_zd_tokens():
    markdown = "[link](https://example.com/a?zd_token=abc&x=1)"

    assert strip_zd_tokens(markdown) == "[link](https://example.com/a&x=1)"


def test_zhihu_cleaning_truncates_repeated_content_start():
    markdown = "# A\n\n正文\n\n# B\n\n更多正文\n\n# A\n\n重复内容"

    assert clean(markdown, "Title") == "# A\n\n正文\n\n# B\n\n更多正文\n"
