from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.core.ai_review import (
    AIVerificationResult,
    feedback_from_ai_verification,
    feedback_from_validation_issues,
    parse_verification_json,
    strip_markdown_fence,
    update_pre_upload_review,
    write_completed_review_report,
)
from src.core.config import REPO_ROOT, ai_config, load_config
from src.core.markdown_links import normalize_markdown_links
from src.core.review_report import inferred_manifest_path, review_report_path
from src.core.review_validation import ValidationResult, validate_reviewed_markdown
from src.integrations.ai_client import AIClient, AIProviderError, AISettings, AITextResponse, resolve_ai_settings


class TextGenerator(Protocol):
    settings: AISettings

    def generate_text(self, system_prompt: str, user_prompt: str) -> AITextResponse:
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

    feedback = ""
    verification: AIVerificationResult | None = None
    validation = validate_reviewed_markdown(path)
    for attempt in range(1, attempts + 1):
        current_markdown = path.read_text(encoding="utf-8")
        response = generator.generate_text(
            rewrite_prompt.replace("{model}", generator.settings.model),
            build_rewrite_user_prompt(raw_markdown, current_markdown, feedback),
        )
        path.write_text(normalize_markdown_links(strip_markdown_fence(response.text)), encoding="utf-8")
        write_completed_review_report(path, manifest_path, model=response.model, provider=response.provider)

        validation = validate_reviewed_markdown(path)
        if not validation.ok:
            feedback = feedback_from_validation_issues(validation.issues)
            verification = None
            continue

        verification = verify_reviewed_article(path, client=generator)
        if verification.passed:
            return AIReviewRunResult(path, validation, verification, attempt)
        feedback = feedback_from_ai_verification(verification)

    return AIReviewRunResult(path, validation, verification, attempts)


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
    response = generator.generate_text(
        verify_prompt,
        build_verify_user_prompt(raw_markdown, reviewed_markdown, validation),
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
    return (manifest_path.parent.parent / raw_path).read_text(encoding="utf-8")


def configured_prompt(config: dict, value_key: str, path_key: str) -> str:
    value = config.get(value_key)
    if isinstance(value, str) and value.strip():
        return value
    path = config.get(path_key)
    if isinstance(path, str) and path.strip():
        prompt_path = Path(path).expanduser()
        if not prompt_path.is_absolute():
            prompt_path = REPO_ROOT / prompt_path
        return prompt_path.read_text(encoding="utf-8")
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
