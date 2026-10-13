from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from src.core.paths import resolve_project_path


class AIProviderConfig(BaseModel):
    api_format: Literal["anthropic", "openai_chat", "openai_responses"] | None = None
    provider_type: Literal["kimi", "minimax", "zhipu", "volcengine", "custom"] | None = None
    model: str
    api_base: str
    api_key: str
    max_output_tokens: int = Field(default=12000, ge=1)
    context_window_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=0.2, ge=0.0, le=2.0)
    timeout_seconds: int = 300
    anthropic_version: str = "2023-06-01"
    vision_capable: bool = False


class AIConfig(BaseModel):
    provider: str = "anthropic"
    image_provider: str | None = None
    max_attempts: int = Field(default=2, ge=1, le=10)
    rewrite_prompt_path: str = "prompts/edit_article.md"
    image_review_prompt_path: str = "prompts/image_review.md"
    reflection_prompt_path: str = "prompts/reflect_article.md"
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


class ReviewPerspectiveLocaleConfig(BaseModel):
    label: str
    description: str = ""
    prompt_path: str
    template_path: str
    output_sections: dict[str, str] = Field(default_factory=dict, exclude=True)
    body_section: str = Field(default="", exclude=True)

    def prompt_metadata(self) -> PromptMetadata:
        from src.core.review.prompt_metadata import PromptMetadata, RequiredHeading, ValidationRule

        return PromptMetadata(
            required_headings=[RequiredHeading(level=1, text=None)],
            validation_rules=[
                ValidationRule("all_images_local", {"required": True}),
                ValidationRule("source_metadata_required_fields", {
                    "fields": ["Source", "Platform", "Author", "Published", "Captured", "Type"],
                    "source_must_be_link": True,
                }),
            ],
        )


class ReviewPerspectiveConfig(ReviewPerspectiveLocaleConfig):
    builtin: bool = False
    localizations: dict[str, ReviewPerspectiveLocaleConfig] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _upgrade_legacy_prompt_profile(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        upgraded = dict(data)
        template_path = str(upgraded.get("template_path") or "")
        if template_path == "prompts/edit_article.md":
            template_path = "prompts/templates/original_article.md"
            upgraded["template_path"] = template_path
        return upgraded

    def localized(self, language: str) -> ReviewPerspectiveLocaleConfig:
        from src.core.localization import normalize_language

        return self.localizations.get(normalize_language(language)) or ReviewPerspectiveLocaleConfig(
            label=self.label,
            description=self.description,
            prompt_path=self.prompt_path,
            template_path=self.template_path,
            output_sections=self.output_sections,
            body_section=self.body_section,
        )

    def prompt_metadata(self, language: str = "en-US") -> PromptMetadata:
        return self.localized(language).prompt_metadata()


def _builtin_perspective_localizations(key: str) -> dict[str, ReviewPerspectiveLocaleConfig]:
    if key == "novice":
        return {
            "zh-CN": ReviewPerspectiveLocaleConfig(
                label="小白视角",
                description="补充必要背景与术语解释，降低首次阅读门槛。",
                prompt_path="prompts/perspectives/novice.md",
                template_path="prompts/templates/novice_article.md",
            ),
            "en-US": ReviewPerspectiveLocaleConfig(
                label="Beginner-friendly",
                description="Add essential context and terminology for a first-time reader.",
                prompt_path="prompts/perspectives/novice.en.md",
                template_path="prompts/templates/novice_article.en.md",
            ),
        }
    return {
        "zh-CN": ReviewPerspectiveLocaleConfig(
            label="基于原文",
            description="保留作者的论证结构，只清理噪音并优化表达。",
            prompt_path="prompts/perspectives/original.md",
            template_path="prompts/templates/original_article.zh.md",
        ),
        "en-US": ReviewPerspectiveLocaleConfig(
            label="Source-faithful",
            description="Preserve the author's argument while removing noise and improving clarity.",
            prompt_path="prompts/perspectives/original.en.md",
            template_path="prompts/templates/original_article.md",
        ),
    }


class PipelineConfig(BaseModel):
    review_mode: Literal["auto_upload", "ai_then_manual"] = "ai_then_manual"
    output_language: Literal["follow_ui", "zh-CN", "en-US", "source"] = "follow_ui"
    active_perspective: str = "original"
    common_prompt_path: str = "prompts/common_review.md"
    common_prompt_paths: dict[str, str] = Field(default_factory=lambda: {
        "zh-CN": "prompts/common_review.md",
        "en-US": "prompts/common_review.en.md",
    })
    classification_prompt_path: str = "prompts/classify_article.md"
    collection_description_prompt_path: str = "prompts/collection_description.md"
    perspectives: dict[str, ReviewPerspectiveConfig] = Field(
        default_factory=lambda: {
            "original": ReviewPerspectiveConfig(
                label="基于原文",
                description="保留作者的论证结构，只清理噪音并优化表达。",
                prompt_path="prompts/perspectives/original.md",
                template_path="prompts/templates/original_article.zh.md",
                builtin=True,
                localizations=_builtin_perspective_localizations("original"),
            ),
            "novice": ReviewPerspectiveConfig(
                label="小白视角",
                description="补充必要背景与术语解释，降低首次阅读门槛。",
                prompt_path="prompts/perspectives/novice.md",
                template_path="prompts/templates/novice_article.md",
                builtin=True,
                localizations=_builtin_perspective_localizations("novice"),
            ),
        }
    )

    @model_validator(mode="before")
    @classmethod
    def _upgrade_review_mode(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("review_mode") == "manual_only":
            upgraded = dict(data)
            upgraded["review_mode"] = "ai_then_manual"
            return upgraded
        return data

    @model_validator(mode="after")
    def _restore_builtin_localizations(self) -> PipelineConfig:
        for key in ("original", "novice"):
            profile = self.perspectives.get(key)
            if profile and profile.prompt_path.endswith(f"/{key}.md"):
                profile.builtin = True
                defaults = _builtin_perspective_localizations(key)
                profile.localizations = {**defaults, **profile.localizations}
        return self

    def resolve_review_prompt(self, perspective: str | None = None, language: str = "en-US") -> tuple[str, PromptMetadata]:
        """Compose hidden system rules, the perspective and natural-language format."""
        from src.core.review.prompt_metadata import parse_prompt_file

        key = perspective or self.active_perspective
        profile = self.perspectives.get(key)
        if profile is None:
            raise ValueError(f"Unknown review perspective: {key}")
        from src.core.localization import normalize_language

        locale = normalize_language(language)
        localized = profile.localized(locale)
        common_path = self.common_prompt_paths.get(locale, self.common_prompt_path)
        common = parse_prompt_file(resolve_project_path(common_path))
        viewpoint = parse_prompt_file(resolve_project_path(localized.prompt_path))
        titles = (
            ("Common constraints", "Review perspective", "Article format")
            if locale == "en-US"
            else ("通用约束", "审阅视角", "文章模板")
        )
        _, template = self.resolve_review_contract(key, locale)
        prompt = "\n\n".join((
            f"# {titles[0]}\n\n" + common.body.strip(),
            f"# {titles[1]}\n\n" + viewpoint.body.strip(),
            f"# {titles[2]}\n\n" + template,
        ))
        return prompt, localized.prompt_metadata()

    def resolve_review_contract(self, perspective: str | None = None, language: str = "en-US") -> tuple[ReviewPerspectiveLocaleConfig, str]:
        from src.core.review.output_contract import article_format_instruction

        key = perspective or self.active_perspective
        profile = self.perspectives.get(key)
        if profile is None:
            raise ValueError(f"Unknown review perspective: {key}")
        localized = profile.localized(language)
        template = resolve_project_path(localized.template_path).read_text(encoding="utf-8")
        return localized, article_format_instruction(template, localized.output_sections)


class CheckpointConfig(BaseModel):
    """LangGraph checkpoint persistence configuration."""

    backend: str = "sqlite"
    """One of ``memory`` (ephemeral), ``sqlite`` (local dev default), or ``postgres`` (production/Docker)."""

    sqlite_path: str = ".noosphere/checkpoints.sqlite"
    """Path to the SQLite checkpoint database when backend is ``sqlite``."""

    postgres_connection_string: str | None = None
    """PostgreSQL connection string when backend is ``postgres``.

    If omitted, the ``DATABASE_URL`` environment variable is used as a fallback
    so Docker deployments do not need to hard-code credentials in ``config.json``.
    """

    @model_validator(mode="before")
    @classmethod
    def _default_backend_from_env(cls, data: Any) -> Any:
        """Default to postgres when ``DATABASE_URL`` is present and backend is not set."""
        if isinstance(data, dict) and "backend" not in data:
            conn = data.get("postgres_connection_string") or os.getenv("DATABASE_URL")
            data["backend"] = "postgres" if conn else "sqlite"
        return data

    def effective_postgres_connection_string(self) -> str | None:
        """Return the configured Postgres connection string or ``DATABASE_URL``."""
        return self.postgres_connection_string or os.getenv("DATABASE_URL")

    @property
    def is_sqlite(self) -> bool:
        return self.backend == "sqlite"

    @property
    def is_postgres(self) -> bool:
        return self.backend == "postgres"

    @property
    def is_memory(self) -> bool:
        return self.backend == "memory"


class SiyuanConfig(BaseModel):
    api_base: str = "http://127.0.0.1:6806"
    default_parent_id: str | None = None
    token: str | None = None


class FirecrawlConfig(BaseModel):
    api_key: str | None = None
    api_base: str = "https://api.firecrawl.dev/v1"


class CrawlerConfig(BaseModel):
    primary: str = "crawl4ai"
    fallback: str | None = None
    firecrawl: FirecrawlConfig = Field(default_factory=FirecrawlConfig)

    @property
    def firecrawl_enabled(self) -> bool:
        return bool(self.firecrawl.api_key)

    @property
    def primary_crawler(self) -> str:
        return str(self.primary).lower()

    @property
    def fallback_crawler(self) -> str | None:
        if self.fallback is not None:
            return str(self.fallback).lower()
        # Auto-derive fallback if not set
        primary = self.primary_crawler
        if primary == "crawl4ai":
            return "firecrawl" if self.firecrawl_enabled else None
        if primary == "firecrawl":
            return "crawl4ai"
        return None


class LocalArchiveConfig(BaseModel):
    enabled: bool = False
    output_dir: str = "archive"


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
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    ai_providers: dict[str, AIProviderConfig] = Field(default_factory=dict)
    siyuan: SiyuanConfig | None = None
    crawler: CrawlerConfig = Field(default_factory=CrawlerConfig)
    checkpoint: CheckpointConfig = Field(default_factory=CheckpointConfig)
    smtp: SMTPConfig | None = None
    local_archive: LocalArchiveConfig | None = None
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
        api_format = provider.api_format
        if api_format is None:
            api_format = "openai_responses" if name == "openai" else "anthropic"
        return {
            "provider": name,
            "api_format": api_format,
            "model": provider.model,
            "api_key": provider.api_key,
            "api_base": provider.api_base,
            "max_output_tokens": provider.max_output_tokens,
            "context_window_tokens": provider.context_window_tokens,
            "temperature": provider.temperature,
            "anthropic_version": provider.anthropic_version,
            "timeout_seconds": provider.timeout_seconds,
            "vision_capable": provider.vision_capable,
        }
