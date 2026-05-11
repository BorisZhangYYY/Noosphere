from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.review_report import build_review_report, inferred_manifest_path, review_report_path
from src.core.review_validation import ValidationIssue, format_validation_issues


# JSON Schema for review_metadata structured output
REVIEW_METADATA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "review": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "removed_noise": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "preserved_sections": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "formatting_changes": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "image_decisions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "suggested_rule_candidates": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["summary", "removed_noise", "preserved_sections", "formatting_changes"],
        },
    },
    "required": ["review"],
}

# JSON Schema for verification structured output
VERIFY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean"},
        "summary": {"type": "string"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string"},
                    "message": {"type": "string"},
                    "revision_instruction": {"type": "string"},
                },
                "required": ["severity", "message"],
            },
        },
    },
    "required": ["passed", "summary", "issues"],
}


@dataclass(frozen=True)
class AIVerificationIssue:
    severity: str
    message: str
    revision_instruction: str


@dataclass(frozen=True)
class AIVerificationResult:
    passed: bool
    summary: str
    issues: list[AIVerificationIssue]
    raw: dict[str, Any]


@dataclass(frozen=True)
class AIRewriteResult:
    markdown: str
    review: dict[str, Any]


def prepare_rewritten_markdown(text: str) -> str:
    return ensure_reviewed_markdown_structure(strip_markdown_fence(text), fallback_review_metadata())


def strip_markdown_fence(text: str) -> str:
    stripped = text.strip()
    match = re.fullmatch(r"```(?:markdown|md)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip() + "\n"
    return stripped + "\n"


def parse_review_metadata_response(text: str) -> dict[str, Any]:
    data = json.loads(extract_json_object(text))
    if not isinstance(data, dict):
        raise ValueError("AI review metadata response must be a JSON object")
    return normalize_review_metadata(data.get("review", data))


def ensure_reviewed_markdown_structure(markdown: str, review: dict[str, Any]) -> str:
    return ensure_main_article_section(ensure_ai_summary_section(markdown, review))


def ensure_ai_summary_section(markdown: str, review: dict[str, Any]) -> str:
    if re.search(r"^##\s+AI Summary\s*$", markdown, flags=re.MULTILINE):
        return markdown

    lines = markdown.rstrip().splitlines()
    separator_index = next((index for index, line in enumerate(lines) if line.strip() == "---"), None)
    if separator_index is None:
        return markdown

    summary = str(review.get("summary") or "").strip() or "AI rewrite completed and structured for upload."
    normalized = lines[: separator_index + 1] + ["", "## AI Summary", "", f"- {summary}", "", "---", ""] + lines[separator_index + 1 :]
    return "\n".join(normalized).rstrip() + "\n"


def ensure_main_article_section(markdown: str) -> str:
    if re.search(r"^##\s+Main Article\s*$", markdown, flags=re.MULTILINE):
        return markdown

    lines = markdown.rstrip().splitlines()
    summary_index = next((index for index, line in enumerate(lines) if line.strip() == "## AI Summary"), None)
    if summary_index is None:
        return markdown

    separator_index = next(
        (index for index in range(summary_index + 1, len(lines)) if lines[index].strip() == "---"),
        None,
    )
    if separator_index is None:
        return markdown

    body_lines = [
        ("### " + line[3:]) if line.startswith("## ") and line.strip() != "## Main Article" else line
        for line in lines[separator_index + 1 :]
    ]
    normalized = lines[: separator_index + 1] + ["", "## Main Article", ""] + body_lines
    return "\n".join(normalized).rstrip() + "\n"


def parse_verification_json(text: str) -> AIVerificationResult:
    data = json.loads(extract_json_object(text))
    if not isinstance(data, dict):
        raise ValueError("AI verification response must be a JSON object")

    issues: list[AIVerificationIssue] = []
    raw_issues = data.get("issues") or []
    if isinstance(raw_issues, list):
        for item in raw_issues:
            if not isinstance(item, dict):
                continue
            issues.append(
                AIVerificationIssue(
                    severity=str(item.get("severity") or "major"),
                    message=str(item.get("message") or "").strip(),
                    revision_instruction=str(item.get("revision_instruction") or "").strip(),
                )
            )
    return AIVerificationResult(
        passed=bool(data.get("passed")) and not issues,
        summary=str(data.get("summary") or "").strip(),
        issues=issues,
        raw=data,
    )


def extract_json_object(text: str) -> str:
    stripped = text.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("AI verification response did not contain a JSON object")
    return stripped[start : end + 1]


def write_completed_review_report(
    reviewed_path: Path,
    manifest_path: Path | None,
    model: str,
    provider: str,
    verification: AIVerificationResult | None = None,
    review: dict[str, Any] | None = None,
) -> Path:
    resolved_manifest_path = manifest_path or inferred_manifest_path(reviewed_path)
    manifest = json.loads(resolved_manifest_path.read_text(encoding="utf-8"))
    report = build_review_report(reviewed_path, resolved_manifest_path, manifest)
    report["status"] = "reviewed"
    report["review"] = normalize_review_metadata(review)
    report["ai"] = {
        "rewrite_provider": provider,
        "rewrite_model": model,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    if verification is not None:
        report["pre_upload_review"] = verification_to_report(verification, model=model, provider=provider)

    output_path = review_report_path(reviewed_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def normalize_review_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return fallback_review_metadata()
    summary = str(value.get("summary") or "").strip() or "AI rewrite completed and structured for upload."
    return {
        "summary": summary,
        "removed_noise": string_list(value.get("removed_noise")) or ["Removed platform/navigation noise, duplicate separators, and unrelated footer content when present."],
        "preserved_sections": string_list(value.get("preserved_sections")) or [f"Preserved the source article's main argument and key sections: {summary}"],
        "formatting_changes": string_list(value.get("formatting_changes")) or ["Normalized the article into the required H1, AI Summary, Main Article, and topic-heading Markdown structure."],
        "image_decisions": string_list(value.get("image_decisions")),
        "suggested_rule_candidates": string_list(value.get("suggested_rule_candidates")),
    }


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def fallback_review_metadata() -> dict[str, Any]:
    return {
        "summary": "AI rewrite completed and structured for upload.",
        "removed_noise": ["AI rewrite was instructed to remove platform noise, footer promotions, duplicated sections, and unrelated recommendations."],
        "preserved_sections": ["AI rewrite was instructed to preserve the source article's main facts, arguments, images, tables, lists, code blocks, and references."],
        "formatting_changes": ["AI rewrite normalized the article to H1, AI Summary, Main Article, and topic-oriented Markdown headings."],
        "image_decisions": ["AI rewrite was instructed to keep meaningful local image links and place them near relevant content."],
        "suggested_rule_candidates": [],
    }


def update_pre_upload_review(
    reviewed_path: Path,
    verification: AIVerificationResult,
    model: str,
    provider: str,
) -> Path:
    output_path = review_report_path(reviewed_path)
    report = json.loads(output_path.read_text(encoding="utf-8"))
    report["pre_upload_review"] = verification_to_report(verification, model=model, provider=provider)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def verification_to_report(verification: AIVerificationResult, model: str, provider: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "passed": verification.passed,
        "summary": verification.summary,
        "issues": [
            {
                "severity": issue.severity,
                "message": issue.message,
                "revision_instruction": issue.revision_instruction,
            }
            for issue in verification.issues
        ],
        "reviewed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def feedback_from_validation_issues(issues: list[ValidationIssue]) -> str:
    if not issues:
        return ""
    return "机器校验未通过，请按以下问题返工：\n" + format_validation_issues(issues)


def feedback_from_ai_verification(result: AIVerificationResult) -> str:
    if result.passed:
        return ""
    lines = ["上传前 AI 审核未通过，请按以下问题返工："]
    if result.summary:
        lines.append(f"- summary: {result.summary}")
    for issue in result.issues:
        instruction = f" {issue.revision_instruction}" if issue.revision_instruction else ""
        lines.append(f"- {issue.severity}: {issue.message}{instruction}")
    return "\n".join(lines)
