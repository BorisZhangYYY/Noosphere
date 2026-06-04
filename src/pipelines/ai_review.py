from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.core.review.ai_review_data import (
    AIVerificationResult,
    REVIEW_METADATA_SCHEMA,
    VERIFY_SCHEMA,
    feedback_from_ai_verification,
    feedback_from_validation_issues,
    fallback_review_metadata,
    parse_review_metadata_response,
    parse_verification_json,
    prepare_rewritten_markdown,
    update_pre_upload_review,
    write_completed_review_report,
)
from src.core.config.config import ai_config, load_config
from src.core.paths import resolve_project_path
from src.core.models.manifest import resolve_manifest_path_entry
from src.core.markdown.links import normalize_markdown_links
from src.core.rules.platform_rules import (
    append_suggested_platform_markers,
    format_noise_hints_context,
    load_noise_hints,
)
from src.core.review.review_report import inferred_manifest_path, review_report_path
from src.core.review.review_validation import ValidationResult, validate_reviewed_markdown
from src.integrations.ai_client import AIClient, AIProviderError, AISettings, AITextResponse, resolve_ai_settings


class TextGenerator(Protocol):
    settings: AISettings

    def generate_text(self, system_prompt: str, user_prompt: str) -> AITextResponse:
        ...

    def generate_structured_text(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict,
    ) -> AITextResponse:
        ...


@dataclass(frozen=True)
class AIReviewRunResult:
    reviewed_path: Path
    validation: ValidationResult
    verification: AIVerificationResult | None
    attempts: int

    @property
    def ok(self) -> bool:
        return self.validation.ok and self.verification is not None and self.verification.passed


def run_ai_review(path: Path, max_attempts: int | None = None, client: TextGenerator | None = None) -> AIReviewRunResult:
    config = load_config()
    settings = client.settings if client else resolve_ai_settings(config)
    generator = client or AIClient(settings)
    manifest_path = inferred_manifest_path(path)
    raw_markdown = raw_markdown_from_manifest(manifest_path)
    ai_settings = ai_config(config)
    attempts = max_attempts or int(ai_settings.get("max_attempts") or 2)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    platform = str((manifest.get("article") or {}).get("platform") or "")
    content_type = str((manifest.get("article") or {}).get("content_type") or "article")
    rewrite_prompt = configured_prompt(
        ai_settings, "rewrite_prompt", "rewrite_prompt_path", platform=platform
    )
    review_metadata_prompt = configured_prompt(
        ai_settings,
        "review_metadata_prompt",
        "review_metadata_prompt_path",
        default_path="prompts/review_metadata.md",
        platform=platform,
    )
    noise_hints_document = noise_hints_from_manifest(manifest_path, manifest)
    noise_hints_context = format_noise_hints_context(noise_hints_document)

    feedback = ""
    verification: AIVerificationResult | None = None
    validation = ValidationResult(path, [])
    resolved_rewrite_prompt = rewrite_prompt.replace("{model}", generator.settings.model)
    for attempt in range(1, attempts + 1):
        # Step 1: Rewrite markdown (first AI call)
        current_markdown = path.read_text(encoding="utf-8")
        response = generator.generate_text(
            resolved_rewrite_prompt,
            build_rewrite_user_prompt(
                raw_markdown,
                current_markdown,
                feedback,
                noise_hints_context=noise_hints_context,
            ),
        )
        reviewed_markdown = normalize_markdown_links(
            prepare_rewritten_markdown(response.text, content_type)
        )

        # Step 2: Generate review metadata (second AI call)
        path.write_text(reviewed_markdown, encoding="utf-8")
        review_metadata = generate_review_metadata(
            generator,
            review_metadata_prompt,
            raw_markdown,
            reviewed_markdown,
            rewrite_prompt=resolved_rewrite_prompt,
            feedback=feedback,
            model=generator.settings.model,
            noise_hints_context=noise_hints_context,
        )
        review_metadata = filter_platform_noise_actions(review_metadata, noise_hints_document)
        report_path = write_completed_review_report(
            path,
            manifest_path,
            model=response.model,
            provider=response.provider,
            review=review_metadata,
        )

        # Machine validation check
        validation = validate_reviewed_markdown(path)
        if not validation.ok:
            feedback = feedback_from_validation_issues(validation.issues)
            verification = None
            continue

        # Step 3: AI pre-upload verification (third AI call)
        verification = verify_reviewed_article(path, client=generator, validation=validation)
        if verification.passed:
            append_suggested_platform_markers(
                platform,
                review_metadata.get("suggested_platform_markers", []),
            )
            return AIReviewRunResult(path, validation, verification, attempt)
        feedback = feedback_from_ai_verification(verification)

    return AIReviewRunResult(path, validation, verification, attempts)


def generate_review_metadata(
    generator: TextGenerator,
    review_metadata_prompt: str,
    raw_markdown: str,
    reviewed_markdown: str,
    *,
    rewrite_prompt: str = "",
    feedback: str = "",
    model: str = "",
    noise_hints_context: str = "",
) -> dict:
    try:
        response = generator.generate_structured_text(
            review_metadata_prompt,
            build_review_metadata_user_prompt(
                raw_markdown,
                reviewed_markdown,
                rewrite_prompt=rewrite_prompt,
                feedback=feedback,
                model=model,
                noise_hints_context=noise_hints_context,
            ),
            REVIEW_METADATA_SCHEMA,
        )
        return parse_review_metadata_response(response.text)
    except Exception:  # noqa: BLE001 - metadata is useful but should not block Markdown review.
        return fallback_review_metadata()


def verify_reviewed_article(
    path: Path,
    client: TextGenerator | None = None,
    validation: ValidationResult | None = None,
) -> AIVerificationResult:
    config = load_config()
    settings = client.settings if client else resolve_ai_settings(config)
    generator = client or AIClient(settings)
    manifest_path = inferred_manifest_path(path)
    raw_markdown = raw_markdown_from_manifest(manifest_path)
    reviewed_markdown = path.read_text(encoding="utf-8")
    validation = validation or validate_reviewed_markdown(path)
    ai_settings = ai_config(config)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    platform = str((manifest.get("article") or {}).get("platform") or "")
    verify_prompt = configured_prompt(
        ai_settings, "verify_prompt", "verify_prompt_path", platform=platform
    )
    response = generator.generate_structured_text(
        verify_prompt,
        build_verify_user_prompt(raw_markdown, reviewed_markdown, validation),
        VERIFY_SCHEMA,
    )
    verification = parse_verification_json(response.text)
    if not validation.ok:
        verification = AIVerificationResult(
            passed=False,
            summary=verification.summary or "Machine validation failed.",
            issues=verification.issues,
            raw=verification.raw,
        )
    if not review_report_path(path).exists():
        write_completed_review_report(path, manifest_path, model=response.model, provider=response.provider)
    update_pre_upload_review(path, verification, model=response.model, provider=response.provider)
    return verification


def raw_markdown_from_manifest(manifest_path: Path) -> str:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = manifest.get("paths") if isinstance(manifest.get("paths"), dict) else {}
    raw_path = paths.get("raw")
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError(f"Raw Markdown path not found in manifest: {manifest_path}")
    return resolve_manifest_path_entry(manifest_path, raw_path).read_text(encoding="utf-8")


def configured_prompt(
    config: dict,
    value_key: str,
    path_key: str,
    default_path: str | None = None,
    platform: str = "",
) -> str:
    # Check platform-specific override first
    platform_overrides = config.get("platform_prompts")
    if platform and isinstance(platform_overrides, dict):
        platform_config = platform_overrides.get(platform, {})
        if isinstance(platform_config, dict):
            platform_value = platform_config.get(value_key)
            if isinstance(platform_value, str) and platform_value.strip():
                return platform_value
            platform_path = platform_config.get(path_key)
            if isinstance(platform_path, str) and platform_path.strip():
                return resolve_project_path(platform_path).read_text(encoding="utf-8")

    # Fall back to global config
    value = config.get(value_key)
    if isinstance(value, str) and value.strip():
        return value
    path = config.get(path_key)
    if isinstance(path, str) and path.strip():
        return resolve_project_path(path).read_text(encoding="utf-8")
    if default_path:
        return resolve_project_path(default_path).read_text(encoding="utf-8")
    raise AIProviderError(f"ai.{value_key} or ai.{path_key} is required")


def build_rewrite_user_prompt(
    raw_markdown: str,
    current_markdown: str,
    feedback: str = "",
    *,
    noise_hints_context: str = "",
) -> str:
    parts = [
        "Below is the original crawled article. Please read it in full:",
        raw_markdown,
        "Below is the current reviewed draft for reference. Rewrite it if the structure is unclear:",
        current_markdown,
    ]
    if noise_hints_context:
        parts.extend(
            [
                noise_hints_context,
                (
                    "For each platform noise hint, decide from context whether it should be removed, kept, "
                    "or rewritten. The hint is not an instruction to delete content."
                ),
            ]
        )
    if feedback:
        parts.extend(["Previous review feedback:", feedback])
    return "\n\n".join(parts)


def build_review_metadata_user_prompt(
    raw_markdown: str,
    reviewed_markdown: str,
    *,
    rewrite_prompt: str = "",
    feedback: str = "",
    model: str = "",
    noise_hints_context: str = "",
) -> str:
    parts = [
        "Original crawled article:",
        raw_markdown,
        "AI-rewritten reviewed Markdown:",
        reviewed_markdown,
    ]
    if rewrite_prompt:
        parts.extend(["AI rewrite instructions:", rewrite_prompt])
    if feedback:
        parts.extend(["Previous feedback (if any):", feedback])
    if model:
        parts.extend([f"(AI model: {model})"])
    if noise_hints_context:
        parts.extend(
            [
                "Platform noise hints and handling requirements:",
                noise_hints_context,
                (
                    "Record your handling of each hint in platform_noise_actions. "
                    "decision must be one of: removed, kept, rewritten, unclear."
                ),
                (
                    "If you discover a new reusable platform marker, add it to suggested_platform_markers. "
                    "text must be short, stable, and reusable—do not use long sentences that only apply to "
                    "this article. reason should only explain why it is suggested."
                ),
            ]
        )
    return "\n\n".join(parts)


def noise_hints_from_manifest(manifest_path: Path, manifest: dict) -> dict:
    paths = manifest.get("paths") if isinstance(manifest.get("paths"), dict) else {}
    noise_hints_path = paths.get("noise_hints")
    if not isinstance(noise_hints_path, str) or not noise_hints_path:
        return {"schema_version": 1, "platform": "", "hints": []}
    return load_noise_hints(resolve_manifest_path_entry(manifest_path, noise_hints_path))


def filter_platform_noise_actions(review_metadata: dict, noise_hints_document: dict) -> dict:
    valid_hint_ids = {
        str(hint.get("hint_id") or "").strip()
        for hint in noise_hints_document.get("hints", [])
        if isinstance(hint, dict)
    }
    filtered = dict(review_metadata)
    actions = review_metadata.get("platform_noise_actions")
    if not isinstance(actions, list) or not valid_hint_ids:
        filtered["platform_noise_actions"] = []
        return filtered
    filtered["platform_noise_actions"] = [
        action
        for action in actions
        if isinstance(action, dict) and str(action.get("hint_id") or "").strip() in valid_hint_ids
    ]
    return filtered


def build_verify_user_prompt(raw_markdown: str, reviewed_markdown: str, validation: ValidationResult) -> str:
    validation_text = "Machine validation passed." if validation.ok else feedback_from_validation_issues(validation.issues)
    return "\n\n".join(
        [
            "Original article:",
            raw_markdown,
            "AI-rewritten reviewed Markdown:",
            reviewed_markdown,
            "Machine validation result:",
            validation_text,
        ]
    )
