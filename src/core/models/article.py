from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


"""Core domain models for extracted articles.

Defines the Article dataclass and related result types (ExtractionResult, UploadResult).
Article is the central immutable object produced by platform extractors and consumed
by pipelines for review, validation, and upload.
"""


@dataclass
class Article:
    """Immutable domain object representing an extracted article.

    The markdown field contains the cleaned body after platform-specific
    extraction and cleaning. Platform extractors produce Article instances;
    pipelines consume them to generate outputs (raw.md, manifest.json, etc.).

    Note:
        to_review_markdown() prepends a metadata block for human editing;
        to_siyuan_markdown() strips metadata because SiYuan sets the doc
        title separately via createDocWithMd.
    """

    platform: str
    platform_label: str
    url: str
    title: str
    markdown: str
    content_type: str = "article"
    author: str | None = None
    published_at: str | None = None
    captured_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds"))
    status_code: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def normalized_body(self) -> str:
        lines = self.markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        title_text = self.title.strip().lstrip("#").strip()

        while lines and not lines[0].strip():
            lines.pop(0)

        for index, line in enumerate(list(lines)):
            stripped = line.strip()
            if not stripped.startswith("#"):
                continue
            heading_text = stripped.lstrip("#").strip()
            if heading_text == title_text:
                del lines[index]
                break

        body = "\n".join(lines).strip()
        return body

    def to_siyuan_markdown(self) -> str:
        # NOTE: Do NOT write metadata header here.
        # The document title is set by createDocWithMd.
        # Metadata fields (url, platform, author, published_at, captured_at)
        # are stored in Article dataclass for reference only.
        return self.normalized_body()

    def to_review_markdown(self) -> str:
        metadata = [
            f"> Source: [{self.url}]({self.url})",
            f"> Platform: {self.platform_label}",
        ]
        if self.author:
            metadata.append(f"> Author: {self.author}")
        if self.published_at:
            metadata.append(f"> Published: {self.published_at}")
        metadata.append(f"> Captured: {self.captured_at}")
        metadata.append(f"> Type: {self.content_type}")

        return "\n".join(
            [
                f"# {self.title}",
                "",
                *metadata,
                "",
                "---",
                "",
                self.normalized_body(),
                "",
            ]
        )


@dataclass
class ExtractionResult:
    article: Article | None
    ok: bool
    error: str | None = None


@dataclass
class UploadResult:
    doc_id: str
    notebook_id: str
    hpath: str
    created: bool
