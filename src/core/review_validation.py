from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.markdown_links import bare_markdown_urls
from src.core.manifest import resolve_manifest_path_entry
from src.core.platform_rules import non_topic_headings
from src.core.review_report import inferred_manifest_path, review_report_path, reviewed_article_id
from src.platforms.wechat_mp import rules as wechat_rules


H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]*)\)")
IMAGE_TARGET_RE = re.compile(r"^(.+?)\s+([\"'][^\"']*[\"'])$")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]*)\)")


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
    if not has_heading(markdown, 2, "AI Summary"):
        issues.append(ValidationIssue("missing_ai_summary", "Reviewed Markdown must contain `## AI Summary`."))
    elif not section_body(markdown, 2, "AI Summary").strip():
        issues.append(ValidationIssue("empty_ai_summary", "`## AI Summary` must contain the AI summary."))
    if not has_heading(markdown, 2, "Main Article"):
        issues.append(ValidationIssue("missing_main_article", "Reviewed Markdown must contain `## Main Article`."))
    elif not section_body(markdown, 2, "Main Article").strip():
        issues.append(ValidationIssue("empty_main_article", "`## Main Article` must contain article body."))
    issues.extend(validate_bare_urls(markdown))
    issues.extend(validate_image_links(markdown, path.parent))

    manifest_path = inferred_manifest_path(path)
    manifest: dict[str, Any] | None = None
    if not manifest_path.exists():
        issues.append(ValidationIssue("missing_manifest", f"Extraction manifest not found: {manifest_path}"))
    else:
        manifest, manifest_issue = read_json_document(manifest_path, "manifest")
        if manifest_issue:
            issues.append(manifest_issue)

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
        issues.extend(validate_platform_review_structure(markdown, manifest_path, manifest, report))

    return ValidationResult(path, issues)


def validate_bare_urls(markdown: str) -> list[ValidationIssue]:
    return [
        ValidationIssue("bare_url", f"Plain URL must be converted to a Markdown link before upload: {url}")
        for url in bare_markdown_urls(markdown)
    ]


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


def validate_platform_review_structure(
    reviewed_markdown: str,
    manifest_path: Path,
    manifest: dict[str, Any],
    report: dict[str, Any],
) -> list[ValidationIssue]:
    article = manifest.get("article") if isinstance(manifest.get("article"), dict) else {}
    if article.get("platform") != "wechat_mp":
        return []

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

    if visible_text_length(raw_body) < wechat_rules.REVIEW_LONG_ARTICLE_MIN_CHARS:
        return issues

    reviewed_headings = topic_headings(cleaned_body)
    raw_headings = topic_headings(raw_body)
    if len(reviewed_headings) < wechat_rules.REVIEW_MIN_LONG_ARTICLE_TOPIC_HEADINGS:
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
