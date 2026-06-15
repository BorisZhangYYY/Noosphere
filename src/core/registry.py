"""Extractor registry and discovery for Noosphere.

Provides a decorator-based registration system where each platform extractor
registers itself at import time. The registry supports URL-to-platform
classification and extractor lookup without hardcoded dictionaries.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol

from src.core.models.article import Article


class ArticleExtractor(Protocol):
    """Protocol that all platform extractors must satisfy.

    BaseArticleExtractor (for web articles) and XExtractor (for oEmbed)
    both implement this protocol. The registry does not care about the
    internal implementation — only that handles() and extract() work.
    """

    platform: str
    platform_label: str
    content_type: str

    def handles(self, url: str) -> bool:
        ...

    async def extract(self, url: str) -> Article:
        ...


ExtractorFactory = Callable[[], ArticleExtractor]


@dataclass
class RegisteredExtractor:
    """Metadata for one registered extractor."""

    platform: str
    label: str
    content_type: str
    url_patterns: list[str]
    factory: ExtractorFactory


class ExtractorRegistry:
    """Central registry for article extractors.

    Usage:
        @register_extractor("wechat_mp", url_patterns=["mp.weixin.qq.com/s/"])
        class WechatMpExtractor(BaseArticleExtractor):
            ...

    Then at runtime:
        registry.classify_url(url) -> "wechat_mp"
        registry.extract(url) -> Article
    """

    def __init__(self) -> None:
        self._extractors: dict[str, RegisteredExtractor] = {}

    def register(
        self,
        platform: str,
        *,
        url_patterns: list[str],
        label: str | None = None,
        content_type: str = "article",
    ) -> Callable[[ExtractorFactory], ExtractorFactory]:
        """Decorator that registers an extractor factory.

        The decorated object must be a callable that returns an
        ArticleExtractor instance (e.g. a class or a factory function).
        """

        def decorator(factory: ExtractorFactory) -> ExtractorFactory:
            instance = factory()
            resolved_label = label or getattr(instance, "platform_label", platform)
            resolved_content_type = getattr(instance, "content_type", content_type)
            self._extractors[platform] = RegisteredExtractor(
                platform=platform,
                label=resolved_label,
                content_type=resolved_content_type,
                url_patterns=url_patterns,
                factory=factory,
            )
            return factory

        return decorator

    def _find_platform(self, url: str) -> str | None:
        """Return the first matching platform for a URL, or None."""
        for platform, meta in self._extractors.items():
            for pattern in meta.url_patterns:
                if pattern in url:
                    return platform
        return None

    def classify_url(self, url: str) -> str:
        """Classify a URL into a registered platform key.

        Raises ValueError if no extractor matches. The error message includes the
        list of supported platforms and their URL patterns so users know why a
        URL was rejected.
        """
        platform = self._find_platform(url)
        if platform is None:
            supported = [
                f"{meta.label} ({', '.join(meta.url_patterns)})"
                for meta in self._extractors.values()
            ]
            lines = [f"Unsupported URL: {url}", "", "Supported platforms:"]
            lines.extend(f"  - {item}" for item in supported)
            raise ValueError("\n".join(lines))
        return platform

    def get_extractor(self, platform: str) -> ArticleExtractor:
        """Instantiate an extractor for the given platform.

        Raises KeyError if the platform is not registered.
        """
        meta = self._extractors[platform]
        return meta.factory()

    async def extract(self, url: str) -> Article:
        """Full pipeline: classify URL + instantiate extractor + extract article."""
        platform = self.classify_url(url)
        extractor = self.get_extractor(platform)
        return await extractor.extract(url)

    def list_platforms(self) -> list[str]:
        """Return all registered platform keys."""
        return list(self._extractors.keys())

    def get_metadata(self, platform: str) -> RegisteredExtractor:
        """Return metadata for a registered platform."""
        return self._extractors[platform]


# Global singleton — import this in every platform module and in the registry consumer.
registry = ExtractorRegistry()

# Convenience decorator bound to the global registry.
def register_extractor(
    platform: str,
    *,
    url_patterns: list[str],
    label: str | None = None,
    content_type: str = "article",
) -> Callable[[ExtractorFactory], ExtractorFactory]:
    """Decorator: register an extractor with the global registry.

    Example:
        @register_extractor("wechat_mp", url_patterns=["mp.weixin.qq.com/s/"])
        class WechatMpExtractor(BaseArticleExtractor):
            ...
    """
    return registry.register(
        platform=platform,
        url_patterns=url_patterns,
        label=label,
        content_type=content_type,
    )
