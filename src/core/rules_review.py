from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.platform_rules import (
    DEFAULT_MARKER_CATEGORY,
    EXAMPLE_RULES_DIR,
    RULES_DIR,
    VALID_MARKER_CATEGORIES,
    generated_marker_id,
    normalize_marker_category,
    platform_rules_path,
    platform_rules_source_path,
    save_platform_rules,
    string_list,
)


@dataclass(frozen=True)
class RulesReviewIssue:
    code: str
    marker_text: str
    message: str
    marker_id: str = ""
    related_text: str = ""
    related_id: str = ""
    safe_apply: bool = False


@dataclass(frozen=True)
class RulesReviewResult:
    platform: str
    source_path: Path
    output_path: Path
    marker_count: int
    final_marker_count: int
    issues: list[RulesReviewIssue]
    applied: bool
    removed_count: int
    normalized_count: int


@dataclass(frozen=True)
class RulesCleanupResult:
    markers: list[dict[str, str]]
    removed_count: int
    normalized_count: int


def review_platform_rules(
    platform: str,
    *,
    apply: bool = False,
    rules_dir: Path = RULES_DIR,
    example_rules_dir: Path = EXAMPLE_RULES_DIR,
) -> RulesReviewResult:
    source_path = platform_rules_source_path(platform, rules_dir, example_rules_dir)
    output_path = platform_rules_path(platform, rules_dir)
    data = read_rules_document(source_path, platform)
    raw_markers = data.get("markers") if isinstance(data.get("markers"), list) else []
    issues = inspect_markers(raw_markers)
    if apply:
        cleanup = cleaned_markers(platform, raw_markers)
        final_markers = cleanup.markers
        removed_count = cleanup.removed_count
        normalized_count = cleanup.normalized_count
    else:
        final_markers = normalized_raw_marker_list(platform, raw_markers)
        removed_count = 0
        normalized_count = 0

    if apply:
        save_platform_rules(
            platform,
            {
                "schema_version": int(data.get("schema_version") or 1),
                "platform": str(data.get("platform") or platform),
                "markers": final_markers,
                "non_topic_headings": string_list(data.get("non_topic_headings")),
            },
            rules_dir,
        )

    return RulesReviewResult(
        platform=platform,
        source_path=source_path,
        output_path=output_path,
        marker_count=len(raw_markers),
        final_marker_count=len(final_markers),
        issues=issues,
        applied=apply,
        removed_count=removed_count,
        normalized_count=normalized_count,
    )


def read_rules_document(path: Path, platform: str) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "platform": platform, "markers": [], "non_topic_headings": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"schema_version": 1, "platform": platform, "markers": [], "non_topic_headings": []}
    return data


def inspect_markers(raw_markers: list[Any]) -> list[RulesReviewIssue]:
    issues: list[RulesReviewIssue] = []
    seen_texts: dict[str, dict[str, str]] = {}
    seen_ids: dict[str, dict[str, str]] = {}
    usable_markers: list[dict[str, str]] = []

    for item in raw_markers:
        if not isinstance(item, dict):
            issues.append(
                RulesReviewIssue(
                    code="invalid_marker",
                    marker_text="",
                    marker_id="",
                    message="Marker entry must be a JSON object.",
                    safe_apply=True,
                )
            )
            continue

        marker = raw_marker_values(item)
        text = marker["text"]
        marker_id = marker["id"]
        category = marker["category"]

        if not text:
            issues.append(
                RulesReviewIssue(
                    code="empty_text",
                    marker_text="",
                    marker_id=marker_id,
                    message="Marker text is empty and can never match article content.",
                    safe_apply=True,
                )
            )
            continue

        if category not in VALID_MARKER_CATEGORIES:
            issues.append(
                RulesReviewIssue(
                    code="invalid_category",
                    marker_text=text,
                    marker_id=marker_id,
                    message=f"Unknown category `{category}` will be normalized to `{DEFAULT_MARKER_CATEGORY}`.",
                    safe_apply=True,
                )
            )

        if text in seen_texts:
            first = seen_texts[text]
            issues.append(
                RulesReviewIssue(
                    code="duplicate_text",
                    marker_text=text,
                    marker_id=marker_id,
                    related_text=first["text"],
                    related_id=first["id"],
                    message="Duplicate marker text; only the first entry is needed.",
                    safe_apply=True,
                )
            )
            continue
        seen_texts[text] = marker

        if marker_id:
            if marker_id in seen_ids:
                first = seen_ids[marker_id]
                issues.append(
                    RulesReviewIssue(
                        code="duplicate_id",
                        marker_text=text,
                        marker_id=marker_id,
                        related_text=first["text"],
                        related_id=first["id"],
                        message="Duplicate marker id; only the first entry is safe to keep.",
                        safe_apply=True,
                    )
                )
                continue
            seen_ids[marker_id] = marker

        if is_short_marker(text):
            issues.append(
                RulesReviewIssue(
                    code="short_marker",
                    marker_text=text,
                    marker_id=marker_id,
                    message="Marker is short and may overmatch; review manually before keeping it.",
                )
            )

        usable_markers.append(marker)

    issues.extend(substring_overlap_issues(usable_markers))
    return issues


def substring_overlap_issues(markers: list[dict[str, str]]) -> list[RulesReviewIssue]:
    issues: list[RulesReviewIssue] = []
    seen_pairs: set[tuple[str, str]] = set()
    for first_index, first in enumerate(markers):
        first_text = first["text"]
        normalized_first = comparable_text(first_text)
        if not normalized_first:
            continue
        for second in markers[first_index + 1 :]:
            second_text = second["text"]
            normalized_second = comparable_text(second_text)
            if not normalized_second or normalized_first == normalized_second:
                continue
            if normalized_first not in normalized_second and normalized_second not in normalized_first:
                continue
            shorter, longer = (first, second) if len(normalized_first) <= len(normalized_second) else (second, first)
            pair = (shorter["text"], longer["text"])
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            issues.append(
                RulesReviewIssue(
                    code="substring_overlap",
                    marker_text=shorter["text"],
                    marker_id=shorter["id"],
                    related_text=longer["text"],
                    related_id=longer["id"],
                    message="One marker is contained in another; choose the safer reusable granularity manually.",
                )
            )
    return issues


def cleaned_markers(platform: str, raw_markers: list[Any]) -> RulesCleanupResult:
    markers: list[dict[str, str]] = []
    seen_texts: set[str] = set()
    seen_ids: set[str] = set()
    removed_count = 0
    normalized_count = 0
    for item in raw_markers:
        if not isinstance(item, dict):
            removed_count += 1
            continue
        values = raw_marker_values(item)
        text = values["text"]
        if not text or text in seen_texts:
            removed_count += 1
            continue
        category = normalize_marker_category(values["category"])
        marker_id = values["id"] or generated_marker_id(platform, text, category)
        if marker_id in seen_ids:
            removed_count += 1
            continue
        seen_texts.add(text)
        seen_ids.add(marker_id)
        if values["category"] not in VALID_MARKER_CATEGORIES:
            normalized_count += 1
        markers.append({"id": marker_id, "text": text, "category": category})
    return RulesCleanupResult(markers, removed_count, normalized_count)


def normalized_raw_marker_list(platform: str, raw_markers: list[Any]) -> list[dict[str, str]]:
    markers: list[dict[str, str]] = []
    for item in raw_markers:
        if not isinstance(item, dict):
            continue
        values = raw_marker_values(item)
        text = values["text"]
        if not text:
            continue
        category = normalize_marker_category(values["category"])
        markers.append(
            {
                "id": values["id"] or generated_marker_id(platform, text, category),
                "text": text,
                "category": category,
            }
        )
    return markers


def raw_marker_values(item: dict[str, Any]) -> dict[str, str]:
    return {
        "id": str(item.get("id") or "").strip(),
        "text": str(item.get("text") or "").strip(),
        "category": str(item.get("category") or "").strip(),
    }


def is_short_marker(text: str) -> bool:
    normalized = comparable_text(text)
    if not normalized:
        return False
    if normalized.isascii():
        return len(normalized) < 4
    return len(normalized) < 3


def comparable_text(text: str) -> str:
    return "".join(str(text or "").casefold().split())


def format_rules_review(result: RulesReviewResult) -> str:
    lines = [
        f"Rules review: {result.platform}",
        f"Source: {result.source_path}",
        f"Output: {result.output_path}",
    ]
    marker_summary = f"Markers: {result.marker_count}"
    if result.applied:
        marker_summary += f" -> {result.final_marker_count}"
    lines.append(marker_summary)
    lines.append(f"Issues: {len(result.issues)}")
    if result.applied:
        lines.append(f"Applied: removed={result.removed_count}, normalized_categories={result.normalized_count}")
    if not result.issues:
        lines.append("")
        lines.append("No issues found.")
        return "\n".join(lines)

    for issue in result.issues:
        lines.extend(["", f"[{issue.code}] {issue.marker_text or issue.marker_id or '(entry)'}"])
        if issue.related_text or issue.related_id:
            lines.append(f"Related: {issue.related_text or issue.related_id}")
        lines.append(f"Action: {'auto-fixable' if issue.safe_apply else 'manual review'}")
        lines.append(f"Reason: {issue.message}")
    return "\n".join(lines)
