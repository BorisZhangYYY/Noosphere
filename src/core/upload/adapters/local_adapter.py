"""Local filesystem archive adapter.

Writes reviewed Markdown and assets to a dated folder structure under a
configurable local directory. No external platform or API is required.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from src.core.config.schema import LocalArchiveConfig
from src.core.markdown.upload_preparer import title_from_markdown
from src.core.paths import resolve_project_path
from src.core.paths.output_paths import safe_filename
from src.core.upload.adapter import UploadAdapter


class LocalAdapter(UploadAdapter):
    """Archive reviewed Markdown to a local folder.

    The archive layout is::

        {archive_dir}/
          2026-06-16_Article_Title/
            reviewed.md
            assets/
              image_01.webp
              ...
    """

    def __init__(self, config: LocalArchiveConfig) -> None:
        self._archive_dir = resolve_project_path(Path(config.output_dir))
        self._archive_dir.mkdir(parents=True, exist_ok=True)

    @property
    def platform_name(self) -> str:
        return "Local Archive"

    async def upload(self, path: Path, title: str | None = None) -> str:
        # Preserve the full reviewed Markdown (including H1) in the local archive.
        markdown = path.read_text(encoding="utf-8")
        fallback = safe_filename(path.stem, fallback="Untitled Article")
        resolved_title = title or title_from_markdown(markdown, fallback)

        safe_title = _safe_dir_name(resolved_title)
        date_prefix = datetime.now().strftime("%Y-%m-%d")
        dir_name = f"{date_prefix}_{safe_title}"

        dest_dir = self._archive_dir / dir_name
        dest_dir = _ensure_unique(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Write the Markdown file
        (dest_dir / "reviewed.md").write_text(markdown, encoding="utf-8")

        # Copy assets if they exist
        assets_src = path.with_name("assets")
        if assets_src.exists() and assets_src.is_dir():
            assets_dst = dest_dir / "assets"
            shutil.copytree(assets_src, assets_dst, dirs_exist_ok=True)

        return str(dest_dir)


def _safe_dir_name(text: str, max_len: int = 60) -> str:
    """Sanitise a string for use as a directory name."""
    cleaned = text.strip()
    for char in ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]:
        cleaned = cleaned.replace(char, "-")
    cleaned = " ".join(cleaned.split())
    cleaned = cleaned.strip(" .-_")
    if not cleaned:
        cleaned = "untitled"
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip(" .-_")
    return cleaned


def _ensure_unique(path: Path) -> Path:
    """Append a numeric suffix if *path* already exists."""
    if not path.exists():
        return path
    parent, name = path.parent, path.name
    stem = name
    counter = 2
    while (parent / f"{stem}_{counter}").exists():
        counter += 1
    return parent / f"{stem}_{counter}"
