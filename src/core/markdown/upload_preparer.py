from __future__ import annotations

import re
from pathlib import Path

from src.core.paths.output_paths import safe_filename

"""Markdown upload preparation.

Reads reviewed Markdown from disk and prepares it for upload by extracting
the title (first H1) and returning title + body separately. The upload
pipeline (src/pipelines/upload.py) uses this to know the document title
independent of the Markdown body.
"""

H1_RE = re.compile(r"^#\s+(.+?)\s*$")


def title_from_markdown(markdown: str, fallback: str) -> str:
    for line in markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        match = H1_RE.match(line.strip())
        if match:
            title = match.group(1).strip()
            if title:
                return title
    return fallback


def markdown_without_leading_h1(markdown: str) -> str:
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    while lines and not lines[0].strip():
        lines.pop(0)

    if lines:
        match = H1_RE.match(lines[0].strip())
        if match:
            lines.pop(0)
            while lines and not lines[0].strip():
                lines.pop(0)

    return "\n".join(lines).strip() + "\n"


def read_markdown_for_upload(path: Path, title: str | None = None) -> tuple[str, str]:
    markdown = path.read_text(encoding="utf-8")
    fallback = safe_filename(path.stem, fallback="Untitled Article")
    resolved_title = title or title_from_markdown(markdown, fallback)
    return resolved_title, markdown_without_leading_h1(markdown)
