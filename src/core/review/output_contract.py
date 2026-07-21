"""Deterministically materialize AI review output through an editable Markdown template."""
from __future__ import annotations

import re
from collections.abc import Mapping

from src.core.review.ai_review_data import strip_markdown_fence
from src.core.review.review_validation import H1_RE, extract_source_metadata_block, section_body


TOKEN_RE = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}")
TRAILING_RULE_RE = re.compile(r"(?:^|\n)\s*(?:---|\*\*\*|___)\s*$")


def validate_output_template(template: str, sections: Mapping[str, str]) -> None:
    required = {"title", "source_metadata", *sections.keys()}
    present = set(TOKEN_RE.findall(template))
    missing = sorted(required - present)
    unknown = sorted(present - required)
    if missing:
        raise ValueError(f"Output template is missing fields: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"Output template contains unknown fields: {', '.join(unknown)}")


def materialize_review_output(
    response: str,
    template: str,
    sections: Mapping[str, str],
) -> str:
    """Render model content into the contract's fixed top-level Markdown skeleton."""
    validate_output_template(template, sections)
    markdown = strip_markdown_fence(response)
    title_match = H1_RE.search(markdown)
    title = title_match.group(1).strip() if title_match else "Untitled"
    metadata = extract_source_metadata_block(markdown) or {}
    source_metadata = "\n".join(f"> {key}: {value}" for key, value in metadata.items())
    values = {
        "title": title,
        "source_metadata": source_metadata,
        **{
            token: _clean_section(section_body(markdown, 2, heading))
            for token, heading in sections.items()
        },
    }

    rendered = TOKEN_RE.sub(lambda match: values.get(match.group(1), ""), template)
    return rendered.strip() + "\n"


def _clean_section(content: str) -> str:
    cleaned = content.strip()
    while cleaned and (match := TRAILING_RULE_RE.search(cleaned)):
        cleaned = cleaned[:match.start()].rstrip()
    return cleaned
