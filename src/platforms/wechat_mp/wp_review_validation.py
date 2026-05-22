from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.core.models.manifest import resolve_manifest_path_entry
from src.core.rules.platform_rules import non_topic_headings
from src.core.review.review_validation import HEADING_RE, MARKDOWN_IMAGE_RE, ValidationIssue, section_body
from src.platforms.wechat_mp import rules


MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]*)\)")


def validate_review_structure(
    reviewed_markdown: str,
    manifest_path: Path,
    manifest: dict[str, Any],
    report: dict[str, Any],
) -> list[ValidationIssue]:
    raw_path = raw_path_from_manifest(manifest_path, manifest)
    if raw_path is None or not raw_path.exists():
        return [
            ValidationIssue(
                "missing_raw_for_structure_review",
                "WeChat review validation needs the raw Markdown path from the extraction manifest.",
            )
        ]
    raw_markdown = raw_path.read_text(encoding="utf-8")
    return validate_wechat_mp_review_structure(reviewed_markdown, raw_markdown, report)


def validate_wechat_mp_review_structure(
    reviewed_markdown: str,
    raw_markdown: str,
    report: dict[str, Any],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    cleaned_body = section_body(reviewed_markdown, 2, "Main Article")
    raw_body = article_body_after_metadata(raw_markdown)

    if visible_text_length(raw_body) < rules.REVIEW_LONG_ARTICLE_MIN_CHARS:
        return issues

    reviewed_headings = topic_headings(cleaned_body)
    if len(reviewed_headings) < rules.REVIEW_MIN_LONG_ARTICLE_TOPIC_HEADINGS:
        issues.append(
            ValidationIssue(
                "weak_article_structure",
                "Long WeChat articles need clearer topical sections before upload. "
                "Add information-rich headings that reflect the article's actual content.",
            )
        )

    review = report.get("review")
    if isinstance(review, dict):
        for field in ("removed_noise", "preserved_sections", "formatting_changes"):
            value = review.get(field)
            if not isinstance(value, list) or not value:
                issues.append(
                    ValidationIssue(
                        "missing_review_details",
                        f"WeChat long-article review report must fill review.{field}.",
                    )
                )
    return issues


def raw_path_from_manifest(manifest_path: Path, manifest: dict[str, Any]) -> Path | None:
    paths = manifest.get("paths")
    if not isinstance(paths, dict):
        return None
    raw_path = paths.get("raw")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    return resolve_manifest_path_entry(manifest_path, raw_path)


def article_body_after_metadata(markdown: str) -> str:
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    parts = normalized.split("\n---\n", 1)
    return parts[1] if len(parts) == 2 else normalized


def visible_text_length(markdown: str) -> int:
    text = MARKDOWN_IMAGE_RE.sub("", markdown)
    text = MARKDOWN_LINK_RE.sub(r"\1", text)
    text = re.sub(r"[#>*_`~\-\[\]()]|\s", "", text)
    return len(text)


def topic_headings(markdown: str) -> list[str]:
    non_topics = non_topic_headings("wechat_mp")
    result: list[str] = []
    for prefix, heading in HEADING_RE.findall(markdown):
        level = len(prefix)
        normalized = normalize_heading(heading)
        if level < 2 or level > 4:
            continue
        if normalized in non_topics:
            continue
        if "发自" in normalized:
            continue
        result.append(normalized)
    return result


def normalize_heading(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().strip("#")).strip()
