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
from src.core.review.image_filter import (
    analyze_images_before_review,
    ensure_relevant_images_present,
    remove_promotion_images_from_markdown,
    update_manifest_with_image_filter,
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
    article_title = str((manifest.get("article") or {}).get("title") or "")

    rewrite_prompt, prompt_metadata = config.ai.resolve_prompt("rewrite_prompt", "rewrite_prompt_path", platform=platform)
    resolved_rewrite_prompt = rewrite_prompt.replace("{model}", generator.settings.model)

    # --- Phase 1: Image Analysis (before text rewrite) ---
    # Use AI Vision to classify images as RELEVANT or PROMOTION
    # This inventory is passed to the text AI so it knows which images to keep
    image_filter_result = None
    if generator.settings.provider in {"anthropic", "compatible", "openai"}:
        paths = manifest.get("paths") if isinstance(manifest.get("paths"), dict) else {}
        assets_rel = paths.get("assets")
        if isinstance(assets_rel, str) and assets_rel:
            assets_dir = resolve_manifest_path_entry(manifest_path, assets_rel)
            if assets_dir.exists() and assets_dir.is_dir():
                try:
                    image_filter_result = await analyze_images_before_review(
                        markdown=raw_markdown,
                        article_title=article_title,
                        article_summary="",  # Will be filled after first review attempt if needed
                        assets_dir=assets_dir,
                        client=generator,  # type: ignore[arg-type]
                    )
                except Exception:
                    image_filter_result = None

    feedback = ""
    validation = ValidationResult(path, [])
    for attempt in range(1, attempts + 1):
        # Build user prompt with image inventory if available
        user_prompt = build_rewrite_user_prompt(
            raw_markdown,
            feedback,
            image_filter_result=image_filter_result,
        )

        response = await generator.generate_text(
            resolved_rewrite_prompt,
            user_prompt,
        )
        reviewed_markdown = normalize_markdown_links(
            prepare_rewritten_markdown(response.text, content_type)
        )

        # --- Phase 2: Remove promotion images and ensure relevant ones are present ---
        if image_filter_result is not None:
            # Remove promotion images from the reviewed markdown
            if image_filter_result.has_promotions:
                reviewed_markdown = remove_promotion_images_from_markdown(
                    reviewed_markdown,
                    image_filter_result.get_promotion_paths(),
                )

            # Ensure relevant images that the AI accidentally dropped are restored
            reviewed_markdown = ensure_relevant_images_present(
                reviewed_markdown,
                image_filter_result.get_relevant_paths(),
            )

        path.write_text(reviewed_markdown, encoding="utf-8")

        validation = validate_reviewed_markdown(path, prompt_metadata)
        if validation.ok:
            if image_filter_result is not None:
                update_manifest_with_image_filter(manifest_path, image_filter_result)
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


def build_rewrite_user_prompt(
    raw_markdown: str,
    feedback: str = "",
    image_filter_result: "ImageFilterResult | None" = None,
) -> str:
    parts = [
        "Below is the original crawled article. Please read it in full:",
        raw_markdown,
    ]

    # Include image inventory so the AI knows which images to keep/remove
    if image_filter_result is not None and (
        image_filter_result.relevant_images or image_filter_result.promotion_images
    ):
        parts.append("")
        parts.append(image_filter_result.build_inventory_for_prompt())
        parts.append(
            "IMPORTANT: When rewriting the article, you MUST preserve all images listed under "
            "'Images to KEEP' by keeping their `![...](...)`` markdown references in the output. "
            "You MUST remove all images listed under 'Images to REMOVE'. Do NOT fabricate new image paths."
        )

    if feedback:
        parts.extend([
            "",
            "Previous rewrite failed validation. Please fix the following issues and rewrite the article:",
            feedback,
        ])
    return "\n\n".join(parts)
