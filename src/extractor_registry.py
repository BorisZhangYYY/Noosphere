from __future__ import annotations

# Import all platform modules to trigger @register_extractor side effects.
# These imports are required for the ExtractorRegistry to populate itself.
from src.platforms.wechat_mp import mp_extractor as _  # noqa: F401
from src.platforms.x import x_extractor as _  # noqa: F401
from src.platforms.xiaoheihe import heihe_extractor as _  # noqa: F401
from src.platforms.zhihu_zhuanlan import zhuanlan_extractor as _  # noqa: F401

from src.core.models.article import Article
from src.core.registry import registry
from src.core.config.config import load_config
from src.core.config.schema import Config


def classify_url(url: str, config: Config | None = None) -> str:
    """Classify a URL into a registered platform key.

    The *config* parameter is kept for backward compatibility but is no longer
    used; URL patterns are now derived from the extractor registry ( populated
    at import time via the ``@register_extractor`` decorator ).
    """
    return registry.classify_url(url)


async def extract_one(url: str, config: Config | None = None) -> Article:
    """Extract an article from a URL using the registered extractor.

    The *config* parameter is kept for backward compatibility but is no longer
    used; the registry selects the extractor based on the URL alone.
    """
    return await registry.extract(url)
