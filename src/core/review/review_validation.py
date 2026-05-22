from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.markdown.links import bare_markdown_urls
from src.core.review.review_report import inferred_manifest_path, review_report_path, reviewed_article_id


H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]*)\)")
IMAGE_TARGET_RE = re.compile(r"^(.+?)\s+([\"'][^\"']*[\"'])$")
HORIZONTAL_RULE_RE = re.compile(r"^\s{0,3}(?:-{3,}|\*{3,}|_{3,})\s*$")


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    path: Path
    issues: list[ValidationIssue]

    @property
    def ok(self) -> bool:
        return not self.issues


def validate_reviewed_markdown(path: Path) -> ValidationResult:
    issues: list[ValidationIssue] = []
    if not path.exists():
        return ValidationResult(path, [ValidationIssue("missing_file", f"Reviewed Markdown file not found: {path}")])

    markdown = path.read_text(encoding="utf-8")
    if not H1_RE.search(markdown):
        issues.append(ValidationIssue("missing_h1", "Reviewed Markdown must start with or contain one H1 title."))

    manifest_path = inferred_manifest_path(path)
    manifest: dict[str, Any] | None = None
    if not manifest_path.exists():
        issues.append(ValidationIssue("missing_manifest", f"Extraction manifest not found: {manifest_path}"))
    else:
        manifest, manifest_issue = read_json_document(manifest_path, "manifest")
        if manifest_issue:
            issues.append(manifest_issue)

    content_type = "article"
    if manifest:
        article_data = manifest.get("article", {})
        if isinstance(article_data, dict):
            content_type = str(article_data.get("content_type", "article"))

    if content_type == "article":
        if not has_heading(markdown, 2, "AI Summary"):
            issues.append(ValidationIssue("missing_ai_summary", "Reviewed Markdown must contain `## AI Summary`."))
        else:
            issues.extend(validate_content_before_ai_summary(markdown))
            if not section_body(markdown, 2, "AI Summary").strip():
                issues.append(ValidationIssue("empty_ai_summary", "`## AI Summary` must contain the AI summary."))
        if not has_heading(markdown, 2, "Main Article"):
            issues.append(ValidationIssue("missing_main_article", "Reviewed Markdown must contain `## Main Article`."))
        elif not section_body(markdown, 2, "Main Article").strip():
            issues.append(ValidationIssue("empty_main_article", "`## Main Article` must contain article body."))
    elif content_type == "social_post":
        pass  # social posts do not require AI Summary / Main Article structure

    issues.extend(validate_bare_urls(markdown))
    issues.extend(validate_image_links(markdown, path.parent))

    report_path = review_report_path(path)
    report: dict[str, Any] | None = None
    if not report_path.exists():
        issues.append(ValidationIssue("missing_review_report", f"Review report not found: {report_path}"))
    else:
        report, report_issue = read_json_document(report_path, "review report")
        if report_issue:
            issues.append(report_issue)
        else:
            issues.extend(validate_review_report_data(report, reviewed_article_id(path)))

    if manifest is not None and report is not None:
        from src.platforms.review_validation import validate_platform_review_structure

"""Deterministic validation rules for reviewed Markdown.

Checks Markdown structure, required sections, image/link integrity, and
dispatches platform-specific validations from src/platforms/<platform>/.

Used by both the ai-review pipeline (as a quality gate) and the standalone
validate CLI command.
"""
        issues.extend(validate_platform_review_structure(markdown, manifest_path, manifest, report))

    return ValidationResult(path, issues)


def validate_bare_urls(markdown: str) -> list[ValidationIssue]:
    return [
        ValidationIssue("bare_url", f"Plain URL must be converted to a Markdown link before upload: {url}")
        for url in bare_markdown_urls(markdown)
    ]


def validate_content_before_ai_summary(markdown: str) -> list[ValidationIssue]:
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    summary_index = next((index for index, line in enumerate(lines) if line.strip() == "## AI Summary"), None)
    if summary_index is None:
        return []

    for line in lines[:summary_index]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# ") or stripped.startswith(">") or HORIZONTAL_RULE_RE.match(stripped):
            continue
        return [
            ValidationIssue(
                "content_before_ai_summary",
                "Reviewed Markdown must not contain article body before `## AI Summary`; "
                "move all body content into `## Main Article`.",
            )
        ]
    return []


def read_json_document(path: Path, label: str) -> tuple[dict[str, Any] | None, ValidationIssue | None]:
    issue_code = f"invalid_{label.replace(' ', '_')}_json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, ValidationIssue(issue_code, f"{label.title()} is not valid JSON: {exc}")
    if not isinstance(data, dict):
        return None, ValidationIssue(issue_code, f"{label.title()} must be a JSON object.")
    return data, None


def validate_review_report(path: Path, expected_article_id: str) -> list[ValidationIssue]:
    report, issue = read_json_document(path, "review report")
    if issue:
        return [issue]
    assert report is not None
    return validate_review_report_data(report, expected_article_id)


def validate_review_report_data(report: dict[str, Any], expected_article_id: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if report.get("article_id") != expected_article_id:
        issues.append(
            ValidationIssue("review_report_article_mismatch", "Review report article_id does not match file name.")
        )
    if report.get("status") != "reviewed":
        issues.append(ValidationIssue("review_report_not_reviewed", "Review report status must be `reviewed`."))

    review = report.get("review")
    if not isinstance(review, dict):
        issues.append(ValidationIssue("missing_review_body", "Review report must contain a review object."))
        return issues
    if not str(review.get("summary") or "").strip():
        issues.append(ValidationIssue("missing_review_summary", "Review report review.summary must be filled."))
    return issues


def validate_image_links(markdown: str, base_dir: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for match in MARKDOWN_IMAGE_RE.finditer(markdown):
        url, _ = split_image_target(match.group(2))
        if not url:
            issues.append(ValidationIssue("empty_image_target", "Markdown image link has an empty target."))
            continue

        parsed = urllib.parse.urlparse(url)
        if parsed.scheme in {"http", "https"}:
            issues.append(
                ValidationIssue("remote_image_link", f"Markdown image must use a local asset path before upload: {url}")
            )
            continue
        if parsed.scheme:
            issues.append(ValidationIssue("unsupported_image_link", f"Unsupported Markdown image link scheme: {url}"))
            continue

        image_path = (base_dir / urllib.parse.unquote(parsed.path)).resolve()
        if not image_path.exists() or not image_path.is_file():
            issues.append(ValidationIssue("missing_local_image", f"Local Markdown image file not found: {url}"))
    return issues


def split_image_target(target: str) -> tuple[str, str | None]:
    stripped = target.strip()
    match = IMAGE_TARGET_RE.match(stripped)
    if match:
        return match.group(1).strip(), match.group(2)
    return stripped, None


def has_heading(markdown: str, level: int, text: str) -> bool:
    target_prefix = "#" * level
    return any(prefix == target_prefix and heading.strip() == text for prefix, heading in HEADING_RE.findall(markdown))


def section_body(markdown: str, level: int, text: str) -> str:
    target_prefix = "#" * level
    matches = list(HEADING_RE.finditer(markdown))
    for index, match in enumerate(matches):
        if match.group(1) != target_prefix or match.group(2).strip() != text:
            continue
        start = match.end()
        end = len(markdown)
        for next_match in matches[index + 1 :]:
            if len(next_match.group(1)) <= level:
                end = next_match.start()
                break
        return markdown[start:end]
    return ""


def format_validation_issues(issues: list[ValidationIssue]) -> str:
    return "\n".join(f"- {issue.code}: {issue.message}" for issue in issues)
