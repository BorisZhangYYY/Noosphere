from __future__ import annotations

from typing import Awaitable, Callable

from src.core.article import Article
from src.core.config import load_config
from src.platforms.wechat_mp import mp_extractor as wechat_mp
from src.platforms.x import x_extractor as x_platform
from src.platforms.xiaoheihe import heihe_extractor as xiaoheihe
from src.platforms.zhihu_zhuanlan import zhuanlan_extractor as zhihu_zhuanlan


Extractor = Callable[[str], Awaitable[Article]]

EXTRACTORS: dict[str, tuple[Callable[[str], bool], Extractor]] = {
    "wechat_mp": (wechat_mp.handles, wechat_mp.extract),
    "x": (x_platform.handles, x_platform.extract),
    "xiaoheihe": (xiaoheihe.handles, xiaoheihe.extract),
    "zhihu_zhuanlan": (zhihu_zhuanlan.handles, zhihu_zhuanlan.extract),
}


def classify_url(url: str, config: dict | None = None) -> str:
    config = config or load_config()

    # Nested config structure: article.* and social_post.*
    for section_key in ("article", "social_post"):
        section = config.get(section_key, {})
        if not isinstance(section, dict):
            continue
        for platform, value in section.items():
            if not isinstance(value, dict):
                continue
            for pattern in value.get("url_patterns", []):
                if pattern in url:
                    if platform not in EXTRACTORS:
                        raise ValueError(f"Configured platform has no extractor: {platform}")
                    return platform

    # Fallback: legacy flat config structure
    for platform, value in config.items():
        if platform in ("siyuan", "article", "social_post") or not isinstance(value, dict):
            continue
        for pattern in value.get("url_patterns", []):
            if pattern in url:
                if platform not in EXTRACTORS:
                    raise ValueError(f"Configured platform has no extractor: {platform}")
                return platform

    for platform, (handles, _) in EXTRACTORS.items():
        if handles(url):
            return platform
    raise ValueError(f"Unsupported URL: {url}")


async def extract_one(url: str, config: dict | None = None) -> Article:
    platform = classify_url(url, config)
    _, extractor = EXTRACTORS[platform]
    return await extractor(url)
