from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.review_report import build_review_report, inferred_manifest_path, review_report_path
from src.core.review_validation import ValidationIssue, format_validation_issues


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


def strip_markdown_fence(text: str) -> str:
    stripped = text.strip()
    match = re.fullmatch(r"```(?:markdown|md)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip() + "\n"
    return stripped + "\n"


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
) -> Path:
    resolved_manifest_path = manifest_path or inferred_manifest_path(reviewed_path)
    manifest = json.loads(resolved_manifest_path.read_text(encoding="utf-8"))
    report = build_review_report(reviewed_path, resolved_manifest_path, manifest)
    report["status"] = "reviewed"
    report["review"] = {
        "summary": "AI rewrite completed and structured for upload.",
        "removed_noise": ["AI rewrite was instructed to remove platform noise, footer promotions, duplicated sections, and unrelated recommendations."],
        "preserved_sections": ["AI rewrite was instructed to preserve the source article's main facts, arguments, images, tables, lists, code blocks, and references."],
        "formatting_changes": ["AI rewrite normalized the article to H1, AI Summary, Main Article, and topic-oriented Markdown headings."],
        "image_decisions": ["AI rewrite was instructed to keep meaningful local image links and place them near relevant content."],
        "suggested_rule_candidates": [],
    }
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
