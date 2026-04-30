from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Article:
    platform: str
    platform_label: str
    url: str
    title: str
    markdown: str
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
        metadata = [
            f"来源：[{self.url}]({self.url})",
            f"平台：{self.platform_label}",
        ]
        if self.author:
            metadata.append(f"作者：{self.author}")
        if self.published_at:
            metadata.append(f"发布时间：{self.published_at}")
        metadata.append(f"抓取时间：{self.captured_at}")

        return "\n".join(
            [
                f"# {self.title.strip()}",
                "",
                "  \n".join(metadata),
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
