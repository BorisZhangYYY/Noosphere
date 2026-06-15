from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.core.paths import resolve_project_path


class AIProviderConfig(BaseModel):
    model: str
    api_base: str
    api_key: str
    max_output_tokens: int = 12000
    temperature: float | None = Field(default=0.2, ge=0.0, le=2.0)
    timeout_seconds: int = 300
    anthropic_version: str = "2023-06-01"


class AIConfig(BaseModel):
    provider: str = "anthropic"
    max_attempts: int = Field(default=2, ge=1, le=10)
    rewrite_prompt_path: str = "prompts/rewrite_article.md"
    image_review_prompt_path: str = "prompts/image_review.md"
    platform_prompts: dict[str, dict[str, str]] = Field(default_factory=dict)

    def resolve_prompt(self, key: str, path_key: str, platform: str = "") -> tuple[str, PromptMetadata]:
        """Resolve prompt with priority: platform override > global config.

        Returns the prompt body text and the parsed metadata from its YAML frontmatter.
        """
        from src.core.review.prompt_metadata import parse_prompt_file, PromptMetadata

        platform_overrides = self.platform_prompts
        if platform and platform in platform_overrides:
            platform_config = platform_overrides[platform]
            if key in platform_config and platform_config[key].strip():
                return platform_config[key], PromptMetadata()
            if path_key in platform_config and platform_config[path_key].strip():
                try:
                    path = resolve_project_path(platform_config[path_key])
                    parsed = parse_prompt_file(path)
                    return parsed.body, parsed.metadata
                except (OSError, FileNotFoundError) as exc:
                    raise ValueError(f"Prompt file not found: {platform_config[path_key]}") from exc

        value = getattr(self, key, None)
        if isinstance(value, str) and value.strip():
            return value, PromptMetadata()
        path = getattr(self, path_key, None)
        if isinstance(path, str) and path.strip():
            try:
                resolved_path = resolve_project_path(path)
                parsed = parse_prompt_file(resolved_path)
                return parsed.body, parsed.metadata
            except (OSError, FileNotFoundError) as exc:
                raise ValueError(f"Prompt file not found: {path}") from exc
        raise ValueError(f"ai.{key} or ai.{path_key} is required")


class SiyuanConfig(BaseModel):
    api_base: str = "http://127.0.0.1:6806"
    default_parent_id: str | None = None
    token: str | None = None


class FirecrawlConfig(BaseModel):
    api_key: str | None = None
    api_base: str = "https://api.firecrawl.dev/v1"


class CrawlerConfig(BaseModel):
    fallback: str | None = None
    firecrawl: FirecrawlConfig = Field(default_factory=FirecrawlConfig)

    @property
    def firecrawl_enabled(self) -> bool:
        return str(self.fallback or "").lower() == "firecrawl" and bool(self.firecrawl.api_key)


class SMTPConfig(BaseModel):
    host: str
    port: int = 587
    user: str
    password: str
    sender_name: str
    allowed_recipients: list[str] = Field(default_factory=list)


class PlatformConfig(BaseModel):
    label: str
    url_patterns: list[str]


class ProxyConfig(BaseModel):
    http: str | None = None
    https: str | None = None


class Config(BaseModel):
    output_dir: str = "outputs"
    ai: AIConfig = Field(default_factory=AIConfig)
    ai_providers: dict[str, AIProviderConfig] = Field(default_factory=dict)
    siyuan: SiyuanConfig | None = None
    crawler: CrawlerConfig = Field(default_factory=CrawlerConfig)
    smtp: SMTPConfig | None = None
    article: dict[str, PlatformConfig] = Field(default_factory=dict)
    social_post: dict[str, PlatformConfig] = Field(default_factory=dict)
    proxy: ProxyConfig | None = None

    @property
    def output_dir_path(self) -> Path:
        return resolve_project_path(self.output_dir)

    def resolve_ai_settings(self, provider_name: str | None = None) -> dict[str, Any]:
        name = provider_name or self.ai.provider
        if name not in self.ai_providers:
            raise ValueError(f"AI provider '{name}' not found in ai_providers config")
        provider = self.ai_providers[name]
        return {
            "provider": name,
            "model": provider.model,
            "api_key": provider.api_key,
            "api_base": provider.api_base,
            "max_output_tokens": provider.max_output_tokens,
            "temperature": provider.temperature,
            "anthropic_version": provider.anthropic_version,
            "timeout_seconds": provider.timeout_seconds,
        }
