"""Upload pipeline — delegates to a configured UploadAdapter."""
from __future__ import annotations

from pathlib import Path

from src.core.upload.factory import create_adapter


async def upload_markdown_file(
    path: Path,
    title: str | None = None,
) -> str:
    """Upload a reviewed Markdown file to the configured note-taking platform.

    The actual upload logic is delegated to the UploadAdapter selected by
    ``create_adapter()`` based on the current configuration.
    """
    adapter = create_adapter()
    return await adapter.upload(path, title)
