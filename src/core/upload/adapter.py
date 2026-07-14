"""Upload adapter abstraction for Noosphere.

Provides a unified interface for uploading reviewed Markdown articles to
various note-taking and knowledge-management platforms. Each platform
implements its own UploadAdapter with full control over asset handling and
document creation semantics.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.models.article import UploadResult


class UploadAdapter(ABC):
    """Abstract base for uploading a reviewed Markdown article to a target platform.

    Implementations own the entire pipeline: reading the Markdown file,
    handling local images, converting content, and creating or updating the
    target document. The caller only needs to invoke ``upload()`` and wait
    for the result.
    """

    @abstractmethod
    async def upload(self, path: Path, title: str | None = None) -> UploadResult:
        """Upload the Markdown file at *path* to the target platform.

        Args:
            path: Path to the reviewed Markdown file.
            title: Optional override for the document title. If omitted, the
                adapter should derive the title from the Markdown content.

        Returns:
            An UploadResult with the platform-specific document identifier.
        """
        ...

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Human-readable platform name for logging and diagnostics."""
        ...
