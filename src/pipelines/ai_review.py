from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.core.config.config import load_config
from src.core.markdown.links import normalize_markdown_links
from src.core.models.manifest import resolve_manifest_path_entry
from src.core.paths import resolve_project_path
from src.core.review.ai_review_data import (
    feedback_from_validation_issues,
    prepare_rewritten_markdown,
    write_completed_review_report,
)
from src.core.review.prompt_metadata import PromptMetadata
from src.core.review.review_report import inferred_manifest_path
from src.core.review.review_validation import ValidationResult, validate_reviewed_markdown
from src.integrations.ai_client import AIClient, AIProviderError, AISettings, AITextResponse, resolve_ai_settings


class TextGenerator(Protocol):
    settings: AISettings

    async def generate_text(self, system_prompt: str, user_prompt: str) -> AITextResponse:
        ...


@dataclass(frozen=True)
class AIReviewRunResult:
    reviewed_path: Path
    validation: ValidationResult
    attempts: int

    @property
    def ok(self) -> bool:
        return self.validation.ok


async def run_ai_review(path: Path, max_attempts: int | None = None, client: TextGenerator | None = None) -> AIReviewRunResult:
    config = load_config()
    settings = client.settings if client else resolve_ai_settings(config)
    generator = client or AIClient(settings)
    manifest_path = inferred_manifest_path(path)
    raw_markdown = raw_markdown_from_manifest(manifest_path)
    attempts = max_attempts or config.ai.max_attempts
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    platform = str((manifest.get("article") or {}).get("platform") or "")
    content_type = str((manifest.get("article") or {}).get("content_type") or "article")
    rewrite_prompt, prompt_metadata = config.ai.resolve_prompt("rewrite_prompt", "rewrite_prompt_path", platform=platform)
    resolved_rewrite_prompt = rewrite_prompt.replace("{model}", generator.settings.model)

    feedback = ""
    validation = ValidationResult(path, [])
    for attempt in range(1, attempts + 1):
        response = await generator.generate_text(
            resolved_rewrite_prompt,
            build_rewrite_user_prompt(raw_markdown, feedback),
        )
        reviewed_markdown = normalize_markdown_links(
            prepare_rewritten_markdown(response.text, content_type)
        )
        path.write_text(reviewed_markdown, encoding="utf-8")

        validation = validate_reviewed_markdown(path, prompt_metadata)
        if validation.ok:
            write_completed_review_report(
                path,
                manifest_path,
                model=response.model,
                provider=response.provider,
            )
            return AIReviewRunResult(path, validation, attempt)
        feedback = feedback_from_validation_issues(validation.issues)

    return AIReviewRunResult(path, validation, attempts)


def raw_markdown_from_manifest(manifest_path: Path) -> str:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = manifest.get("paths") if isinstance(manifest.get("paths"), dict) else {}
    raw_path = paths.get("raw")
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError(f"Raw Markdown path not found in manifest: {manifest_path}")
    return resolve_manifest_path_entry(manifest_path, raw_path).read_text(encoding="utf-8")


def build_rewrite_user_prompt(raw_markdown: str, feedback: str = "") -> str:
    parts = [
        "Below is the original crawled article. Please read it in full:",
        raw_markdown,
    ]
    if feedback:
        parts.extend([
            "Previous rewrite failed validation. Please fix the following issues and rewrite the article:",
            feedback,
        ])
    return "\n\n".join(parts)
