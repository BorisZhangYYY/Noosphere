"""Upload adapter abstraction for Noosphere.

Provides a unified interface for uploading reviewed Markdown articles to
various note-taking and knowledge-management platforms. Each platform
implements its own UploadAdapter with full control over asset handling and
document creation semantics.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class UploadAdapter(ABC):
    """Abstract base for uploading a reviewed Markdown article to a target platform.

    Implementations own the entire pipeline: reading the Markdown file,
    handling local images, converting content, and creating or updating the
    target document. The caller only needs to invoke ``upload()`` and wait
    for the result.
    """

    @abstractmethod
    async def upload(self, path: Path, title: str | None = None) -> str:
        """Upload the Markdown file at *path* to the target platform.

        Args:
            path: Path to the reviewed Markdown file.
            title: Optional override for the document title. If omitted, the
                adapter should derive the title from the Markdown content.

        Returns:
            A platform-specific identifier for the created/updated document
            (e.g. SiYuan hpath, Notion page URL, Obsidian file path).
        """
        ...

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Human-readable platform name for logging and diagnostics."""
        ...
