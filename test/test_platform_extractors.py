from __future__ import annotations

from src.platforms.wechat_mp import mp_extractor
from src.platforms.zhihu_zhuanlan import zhuanlan_extractor
from src.wechat_mp import handles as legacy_wechat_handles
from src.zhihu_zhuanlan import handles as legacy_zhihu_handles


def test_explicit_platform_extractor_modules_handle_known_urls():
    assert mp_extractor.handles("https://mp.weixin.qq.com/s/example")
    assert zhuanlan_extractor.handles("https://zhuanlan.zhihu.com/p/123")


def test_legacy_platform_packages_forward_to_new_platform_modules():
    assert legacy_wechat_handles("https://mp.weixin.qq.com/s/example")
    assert legacy_zhihu_handles("https://zhuanlan.zhihu.com/p/123")
