from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.markdown.links import bare_markdown_urls
from src.core.review.prompt_metadata import PromptMetadata
from src.core.review.review_report import inferred_manifest_path


H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]*)\)")
IMAGE_TARGET_RE = re.compile(r"^(.+?)\s+([\"'][^\"']*[\"'])$")
HORIZONTAL_RULE_RE = re.compile(r"^\s{0,3}(?:-{3,}|\*{3,}|_{3,})\s*$")
SOURCE_METADATA_LINE_RE = re.compile(r"^>\s*(.+?)\s*:\s*(.+?)\s*$")
CODE_FENCE_RE = re.compile(r"^\s{0,3}(```|~~~)")


def _code_block_regions(markdown: str) -> list[tuple[int, int]]:
    """Return (start, end) character ranges of fenced code blocks."""
    regions: list[tuple[int, int]] = []
    in_block = False
    fence = ""
    start = 0
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    char_index = 0
    for line in lines:
        match = CODE_FENCE_RE.match(line)
        if match:
            if not in_block:
                in_block = True
                fence = match.group(1)
                start = char_index
            elif line.strip().startswith(fence):
                in_block = False
                regions.append((start, char_index + len(line)))
        char_index += len(line) + 1  # +1 for the newline
    if in_block:
        regions.append((start, len(markdown)))
    return regions


def _find_headings_outside_code_blocks(markdown: str) -> list[re.Match[str]]:
    """Return HEADING_RE matches that are not inside fenced code blocks."""
    regions = _code_block_regions(markdown)
    matches: list[re.Match[str]] = []
    for match in HEADING_RE.finditer(markdown):
        if not any(start <= match.start() < end for start, end in regions):
            matches.append(match)
    return matches


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


def validate_reviewed_markdown(path: Path, prompt_metadata: PromptMetadata | None = None) -> ValidationResult:
    issues: list[ValidationIssue] = []
    if not path.exists():
        return ValidationResult(path, [ValidationIssue("missing_file", f"Reviewed Markdown file not found: {path}")])

    markdown = path.read_text(encoding="utf-8")

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

    # Use prompt metadata if provided; otherwise fall back to legacy hardcoded rules.
    if prompt_metadata is not None:
        issues.extend(_validate_from_metadata(markdown, prompt_metadata, content_type))
    else:
        issues.extend(_validate_legacy(markdown, content_type))

    issues.extend(validate_bare_urls(markdown))
    issues.extend(validate_image_links(markdown, path.parent))

    return ValidationResult(path, issues)


def _validate_from_metadata(markdown: str, metadata: PromptMetadata, content_type: str) -> list[ValidationIssue]:
    """Validate Markdown using rules from the prompt metadata."""
    issues: list[ValidationIssue] = []

    # Check required headings
    for heading in metadata.required_headings:
        if heading.level == 1:
            if not H1_RE.search(markdown):
                issues.append(ValidationIssue("missing_h1", "Reviewed Markdown must start with or contain one H1 title."))
        elif heading.text and not has_heading(markdown, heading.level, heading.text):
            issues.append(ValidationIssue(
                f"missing_{heading.text.lower().replace(' ', '_')}",
                f"Reviewed Markdown must contain `{'#' * heading.level} {heading.text}`."
            ))
        elif heading.text and not section_body(markdown, heading.level, heading.text).strip():
            issues.append(ValidationIssue(
                f"empty_{heading.text.lower().replace(' ', '_')}",
                f"`{'#' * heading.level} {heading.text}` must contain content."
            ))

    # Check validation rules
    for rule in metadata.validation_rules:
        if rule.rule_type == "no_content_before_heading":
            anchor = rule.params.get("heading")
            if anchor:
                issues.extend(validate_content_before_heading(markdown, anchor))
        elif rule.rule_type == "all_images_local":
            # Handled by validate_image_links in the main validator
            pass
        elif rule.rule_type == "source_metadata_required_fields":
            fields = rule.params.get("fields", ["Source", "Platform", "Author", "Published", "Captured", "Type"])
            source_must_be_link = rule.params.get("source_must_be_link", True)
            issues.extend(validate_source_metadata_block(markdown, required_fields=fields, source_must_be_link=source_must_be_link))
        elif rule.rule_type == "main_article_subheadings_min_level":
            min_level = int(rule.params.get("min_level", 3))
            issues.extend(validate_main_article_heading_hierarchy(markdown, min_level=min_level))

    return issues


def _validate_legacy(markdown: str, content_type: str) -> list[ValidationIssue]:
    """Legacy hardcoded validation rules for backward compatibility."""
    issues: list[ValidationIssue] = []

    if not H1_RE.search(markdown):
        issues.append(ValidationIssue("missing_h1", "Reviewed Markdown must start with or contain one H1 title."))

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
        issues.extend(validate_source_metadata_block(markdown))
        issues.extend(validate_main_article_heading_hierarchy(markdown))
    elif content_type == "social_post":
        pass  # social posts do not require AI Summary / Main Article structure for now

    return issues


def validate_bare_urls(markdown: str) -> list[ValidationIssue]:
    return [
        ValidationIssue("bare_url", f"Plain URL must be converted to a Markdown link before upload: {url}")
        for url in bare_markdown_urls(markdown)
    ]


def validate_content_before_heading(markdown: str, heading_text: str) -> list[ValidationIssue]:
    """Ensure no article body content appears before the specified heading."""
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    heading_line = f"{'#' * 2} {heading_text}"
    heading_index = next((index for index, line in enumerate(lines) if line.strip() == heading_line), None)
    if heading_index is None:
        return []

    for line in lines[:heading_index]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# ") or stripped.startswith(">") or HORIZONTAL_RULE_RE.match(stripped):
            continue
        return [
            ValidationIssue(
                "content_before_heading",
                f"Reviewed Markdown must not contain article body before `## {heading_text}`; "
                f"move all body content into the appropriate section.",
            )
        ]
    return []


# Backward-compatible alias
def validate_content_before_ai_summary(markdown: str) -> list[ValidationIssue]:
    """Legacy alias for validate_content_before_heading('AI Summary')."""
    return validate_content_before_heading(markdown, "AI Summary")


def read_json_document(path: Path, label: str) -> tuple[dict[str, Any] | None, ValidationIssue | None]:
    issue_code = f"invalid_{label.replace(' ', '_')}_json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, ValidationIssue(issue_code, f"{label.title()} is not valid JSON: {exc}")
    if not isinstance(data, dict):
        return None, ValidationIssue(issue_code, f"{label.title()} must be a JSON object.")
    return data, None


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
    return any(
        match.group(1) == target_prefix and match.group(2).strip() == text
        for match in _find_headings_outside_code_blocks(markdown)
    )


def section_body(markdown: str, level: int, text: str) -> str:
    target_prefix = "#" * level
    matches = _find_headings_outside_code_blocks(markdown)
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


def extract_source_metadata_block(markdown: str) -> dict[str, str] | None:
    """Return the first blockquote after the H1 title as a {field: value} dict.

    Returns None if no valid source metadata block is found.
    """
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    h1_index = next(
        (index for index, line in enumerate(lines) if H1_RE.match(line.strip())),
        None,
    )
    if h1_index is None:
        return None

    # Skip blank lines between the H1 and the metadata block
    start_index = h1_index + 1
    while start_index < len(lines) and not lines[start_index].strip():
        start_index += 1

    metadata: dict[str, str] = {}
    for line in lines[start_index:]:
        stripped = line.strip()
        if not stripped or HORIZONTAL_RULE_RE.match(stripped):
            break
        match = SOURCE_METADATA_LINE_RE.match(stripped)
        if match:
            metadata[match.group(1).strip()] = match.group(2).strip()
        else:
            break
    return metadata if metadata else None


def validate_source_metadata_block(
    markdown: str,
    required_fields: list[str] | None = None,
    source_must_be_link: bool = True,
) -> list[ValidationIssue]:
    """Validate the source metadata blockquote after the H1 title."""
    issues: list[ValidationIssue] = []
    required_fields = required_fields or ["Source", "Platform", "Author", "Published", "Captured", "Type"]

    block = extract_source_metadata_block(markdown)
    if block is None:
        return [
            ValidationIssue(
                "missing_source_metadata",
                "Reviewed Markdown must have a source metadata blockquote immediately after the H1 title.",
            )
        ]

    for field in required_fields:
        if field not in block:
            issues.append(
                ValidationIssue(
                    "missing_source_metadata_field",
                    f"Source metadata block must include `> {field}: ...`.",
                )
            )

    if source_must_be_link and "Source" in block:
        source_value = block["Source"]
        if not re.search(r"\[([^\]]+)\]\(([^)]+)\)", source_value):
            issues.append(
                ValidationIssue(
                    "source_url_not_linked",
                    "Source metadata field must contain the article URL as a Markdown link: `> Source: [URL](URL)`.",
                )
            )

    return issues


def validate_main_article_heading_hierarchy(
    markdown: str,
    min_level: int = 3,
) -> list[ValidationIssue]:
    """Ensure headings inside `## Main Article` are at least `min_level`."""
    issues: list[ValidationIssue] = []
    matches = _find_headings_outside_code_blocks(markdown)

    main_index = next(
        (
            index
            for index, match in enumerate(matches)
            if match.group(1) == "##" and match.group(2).strip() == "Main Article"
        ),
        None,
    )
    if main_index is None:
        return issues

    for match in matches[main_index + 1 :]:
        level = len(match.group(1))
        text = match.group(2).strip()

        if level < min_level:
            issues.append(
                ValidationIssue(
                    "invalid_main_article_heading_level",
                    f"Heading under `## Main Article` must be `{'#' * min_level}` or deeper, "
                    f"but found `{'#' * level} {text}`.",
                )
            )
        if level <= 2:
            # An H2 (or H1) after Main Article ends the section; report it once and stop scanning.
            break

    return issues


def format_validation_issues(issues: list[ValidationIssue]) -> str:
    return "\n".join(f"- {issue.code}: {issue.message}" for issue in issues)
