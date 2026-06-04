from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from src.core.review.review_report import inferred_manifest_path, review_report_path
from src.core.review.review_validation import ValidationIssue, format_validation_issues

"""Data structures and parsing helpers for AI rewrite output.

Defines helpers for normalizing AI-rewritten Markdown into the required
reviewed structure. This module does not orchestrate the review pipeline;
that lives in src/pipelines/ai_review.py.
"""


def prepare_rewritten_markdown(text: str, content_type: str = "article") -> str:
    return ensure_reviewed_markdown_structure(strip_markdown_fence(text), content_type)


def strip_markdown_fence(text: str) -> str:
    stripped = text.strip()
    match = re.fullmatch(r"```(?:markdown|md)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip() + "\n"
    return stripped + "\n"


def ensure_reviewed_markdown_structure(markdown: str, content_type: str = "article") -> str:
    if content_type == "social_post":
        return markdown
    return remove_empty_generic_body_headings(ensure_main_article_section(ensure_ai_summary_section(markdown)))


def ensure_ai_summary_section(markdown: str) -> str:
    if re.search(r"^##\s+AI Summary\s*$", markdown, flags=re.MULTILINE):
        return markdown

    lines = markdown.rstrip().splitlines()
    separator_index = next((index for index, line in enumerate(lines) if line.strip() == "---"), None)
    if separator_index is None:
        return markdown

    summary = "AI rewrite completed and structured for upload."
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


def remove_empty_generic_body_headings(markdown: str) -> str:
    lines = markdown.rstrip().splitlines()
    result: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.match(r"^(#{2,6})\s+(.+?)\s*$", line)
        if match and normalize_generic_heading(match.group(2)) in {"正文"}:
            next_index = index + 1
            while next_index < len(lines) and not lines[next_index].strip():
                next_index += 1
            if next_index < len(lines) and re.match(r"^#{2,6}\s+", lines[next_index]):
                index = next_index
                while result and not result[-1].strip():
                    result.pop()
                if result:
                    result.append("")
                continue
        result.append(line)
        index += 1
    return "\n".join(result).rstrip() + "\n"


def normalize_generic_heading(text: str) -> str:
    return re.sub(r"\s+", "", text.strip().strip("#"))


def write_completed_review_report(
    reviewed_path: Path,
    manifest_path: Path | None,
    model: str,
    provider: str,
) -> Path:
    from src.core.review.review_report import build_review_report

    resolved_manifest_path = manifest_path or inferred_manifest_path(reviewed_path)
    manifest = json.loads(resolved_manifest_path.read_text(encoding="utf-8"))
    report = build_review_report(reviewed_path, resolved_manifest_path, manifest)
    report["status"] = "reviewed"
    report["ai"] = {
        "rewrite_provider": provider,
        "rewrite_model": model,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    output_path = review_report_path(reviewed_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


MAX_FEEDBACK_CHARS = 2000


def feedback_from_validation_issues(issues: list[ValidationIssue]) -> str:
    if not issues:
        return ""
    text = "Machine validation failed. Please fix the following issues:\n" + format_validation_issues(issues)
    if len(text) > MAX_FEEDBACK_CHARS:
        text = text[:MAX_FEEDBACK_CHARS] + "\n... (truncated)"
    return text
