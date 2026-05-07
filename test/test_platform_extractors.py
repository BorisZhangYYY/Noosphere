from __future__ import annotations

from src.platforms.wechat_mp import mp_extractor
from src.platforms.zhihu_zhuanlan import zhuanlan_extractor


def test_explicit_platform_extractor_modules_handle_known_urls():
    assert mp_extractor.handles("https://mp.weixin.qq.com/s/example")
    assert zhuanlan_extractor.handles("https://zhuanlan.zhihu.com/p/123")
