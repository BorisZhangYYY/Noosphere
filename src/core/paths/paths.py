from __future__ import annotations

from pathlib import Path

from src.core.config.config import configured_output_dir, load_config
from src.core.paths import project_root

"""Application-level path configuration for Noosphere.

Provides a centralized ``Paths`` class that encapsulates every directory
and file layout used by the application, plus a lazy singleton for the
common case where the caller does not need a custom output directory.
"""


class Paths:
    """Centralized path configuration for Noosphere application data.

    Directory layout under ``output_dir``:

        {output_dir}/
        └── <article_id>/
            ├── raw.md
            ├── reviewed.md
            ├── manifest.json
            ├── review.json
            ├── email_report.json
            └── assets/
    """

    def __init__(self, output_dir: str | Path | None = None) -> None:
        self._output_dir = Path(output_dir).resolve() if output_dir is not None else None

    @property
    def output_dir(self) -> Path:
        """Root directory for all article workspaces."""
        if self._output_dir is not None:
            return self._output_dir
        return configured_output_dir(load_config())

    @property
    def prompts_dir(self) -> Path:
        """Directory containing prompt templates."""
        return project_root() / "prompts"

    @property
    def crawl4ai_runtime_dir(self) -> Path:
        """Crawl4AI runtime cache directory."""
        return project_root() / ".crawl4ai-runtime"

    # Article-scoped paths

    def article_dir(self, article_id: str) -> Path:
        """Workspace directory for a specific article."""
        return self.output_dir / article_id

    def article_raw_path(self, article_id: str) -> Path:
        return self.article_dir(article_id) / "raw.md"

    def article_reviewed_path(self, article_id: str) -> Path:
        return self.article_dir(article_id) / "reviewed.md"

    def article_manifest_path(self, article_id: str) -> Path:
        return self.article_dir(article_id) / "manifest.json"

    def article_review_path(self, article_id: str) -> Path:
        return self.article_dir(article_id) / "review.json"

    def article_email_report_path(self, article_id: str) -> Path:
        return self.article_dir(article_id) / "email_report.json"

    def article_assets_dir(self, article_id: str) -> Path:
        return self.article_dir(article_id) / "assets"

    def ensure_article_dirs(self, article_id: str) -> None:
        """Create the article workspace directory and its assets subdirectory."""
        self.article_dir(article_id).mkdir(parents=True, exist_ok=True)
        self.article_assets_dir(article_id).mkdir(parents=True, exist_ok=True)

    def ensure_crawl4ai_runtime_dir(self) -> Path:
        """Create and return the Crawl4AI runtime directory."""
        path = self.crawl4ai_runtime_dir
        path.mkdir(parents=True, exist_ok=True)
        return path


_paths: Paths | None = None


def get_paths() -> Paths:
    """Return the global ``Paths`` singleton (lazy-initialized)."""
    global _paths
    if _paths is None:
        _paths = Paths()
    return _paths
