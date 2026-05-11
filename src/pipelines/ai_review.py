from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.core.ai_review import (
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
from src.core.config import REPO_ROOT, ai_config, load_config
from src.core.manifest import resolve_manifest_path_entry
from src.core.markdown_links import normalize_markdown_links
from src.core.review_report import inferred_manifest_path, review_report_path
from src.core.review_validation import ValidationResult, validate_reviewed_markdown
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
    rewrite_prompt = configured_prompt(ai_settings, "rewrite_prompt", "rewrite_prompt_path")
    review_metadata_prompt = configured_prompt(
        ai_settings,
        "review_metadata_prompt",
        "review_metadata_prompt_path",
        default_path="prompts/review_metadata.md",
    )

    feedback = ""
    verification: AIVerificationResult | None = None
    validation = validate_reviewed_markdown(path)
    resolved_rewrite_prompt = rewrite_prompt.replace("{model}", generator.settings.model)
    for attempt in range(1, attempts + 1):
        # Step 1: Rewrite markdown (first AI call)
        current_markdown = path.read_text(encoding="utf-8")
        response = generator.generate_text(
            resolved_rewrite_prompt,
            build_rewrite_user_prompt(raw_markdown, current_markdown, feedback),
        )
        reviewed_markdown = normalize_markdown_links(prepare_rewritten_markdown(response.text))

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
        )
        write_completed_review_report(
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
        verification = verify_reviewed_article(path, client=generator)
        if verification.passed:
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
            ),
            REVIEW_METADATA_SCHEMA,
        )
        return parse_review_metadata_response(response.text)
    except Exception:  # noqa: BLE001 - metadata is useful but should not block Markdown review.
        return fallback_review_metadata()


def verify_reviewed_article(path: Path, client: TextGenerator | None = None) -> AIVerificationResult:
    config = load_config()
    settings = client.settings if client else resolve_ai_settings(config)
    generator = client or AIClient(settings)
    manifest_path = inferred_manifest_path(path)
    raw_markdown = raw_markdown_from_manifest(manifest_path)
    reviewed_markdown = path.read_text(encoding="utf-8")
    validation = validate_reviewed_markdown(path)
    ai_settings = ai_config(config)
    verify_prompt = configured_prompt(ai_settings, "verify_prompt", "verify_prompt_path")
    response = generator.generate_structured_text(
        verify_prompt,
        build_verify_user_prompt(raw_markdown, reviewed_markdown, validation),
        VERIFY_SCHEMA,
    )
    verification = parse_verification_json(response.text)
    if not validation.ok:
        verification = AIVerificationResult(
            passed=False,
            summary=verification.summary or "机器校验未通过。",
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


def configured_prompt(config: dict, value_key: str, path_key: str, default_path: str | None = None) -> str:
    value = config.get(value_key)
    if isinstance(value, str) and value.strip():
        return value
    path = config.get(path_key)
    if isinstance(path, str) and path.strip():
        prompt_path = Path(path).expanduser()
        if not prompt_path.is_absolute():
            prompt_path = REPO_ROOT / prompt_path
        return prompt_path.read_text(encoding="utf-8")
    if default_path:
        return (REPO_ROOT / default_path).read_text(encoding="utf-8")
    raise AIProviderError(f"ai.{value_key} or ai.{path_key} is required")


def build_rewrite_user_prompt(raw_markdown: str, current_markdown: str, feedback: str = "") -> str:
    parts = [
        "下面是原始抓取文章，请完整阅读：",
        raw_markdown,
        "下面是当前 reviewed 草稿，可以作为参考，但如果结构不清晰必须重写：",
        current_markdown,
    ]
    if feedback:
        parts.extend(["上一轮审核反馈：", feedback])
    return "\n\n".join(parts)


def build_review_metadata_user_prompt(
    raw_markdown: str,
    reviewed_markdown: str,
    *,
    rewrite_prompt: str = "",
    feedback: str = "",
    model: str = "",
) -> str:
    parts = [
        "原始抓取文章：",
        raw_markdown,
        "AI 改写后的 reviewed Markdown：",
        reviewed_markdown,
    ]
    if rewrite_prompt:
        parts.extend(["AI 改写指令：", rewrite_prompt])
    if feedback:
        parts.extend(["上一轮反馈（如有）：", feedback])
    if model:
        parts.extend([f"（AI model: {model}）"])
    return "\n\n".join(parts)


def build_verify_user_prompt(raw_markdown: str, reviewed_markdown: str, validation: ValidationResult) -> str:
    validation_text = "机器校验通过。" if validation.ok else feedback_from_validation_issues(validation.issues)
    return "\n\n".join(
        [
            "原始文章：",
            raw_markdown,
            "AI 改写后的 reviewed Markdown：",
            reviewed_markdown,
            "机器校验结果：",
            validation_text,
        ]
    )
