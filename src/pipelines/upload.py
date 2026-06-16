"""Upload pipeline — delegates to a configured UploadAdapter."""
from __future__ import annotations

from pathlib import Path

from src.core.upload.adapter import UploadAdapter
from src.core.upload.factory import create_adapter


async def upload_markdown_file(
    path: Path,
    title: str | None = None,
    adapter: UploadAdapter | None = None,
) -> str:
    """Upload a reviewed Markdown file to the configured note-taking platform.

    If *adapter* is provided, it is used directly; otherwise ``create_adapter()``
    selects one from the current configuration.
    """
    adapter = adapter or create_adapter()
    return await adapter.upload(path, title)
