"""Upload pipeline — delegates to a configured UploadAdapter."""
from __future__ import annotations

import warnings
from pathlib import Path

from src.core.upload.adapter import UploadAdapter
from src.core.upload.factory import create_adapter

warnings.warn(
    "src.pipelines.upload is deprecated; use src.graph.graph.run_upload_graph instead.",
    DeprecationWarning,
    stacklevel=2,
)


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
