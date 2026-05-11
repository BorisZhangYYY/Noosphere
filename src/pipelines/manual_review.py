from __future__ import annotations

from pathlib import Path

from src.core.review_report import write_review_report


def create_manual_review_report(
    reviewed_path: Path,
    manifest_path: Path | None = None,
    overwrite: bool = False,
) -> Path:
    return write_review_report(reviewed_path, manifest_path=manifest_path, overwrite=overwrite)
