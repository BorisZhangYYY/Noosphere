from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

"""Review report persistence.

Handles reading and writing of review.json, the article-specific status
record produced by the AI review pipeline.
"""

SCHEMA_VERSION = 1


def inferred_manifest_path(reviewed_path: Path) -> Path:
    return reviewed_path.with_name("manifest.json")


def review_report_path(reviewed_path: Path) -> Path:
    return reviewed_path.with_name("review.json")


def reviewed_article_id(reviewed_path: Path) -> str:
    return reviewed_path.parent.name


def build_review_report(
    reviewed_path: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
    created_at: str | None = None,
) -> dict[str, Any]:
    article_id = str(manifest.get("article_id") or reviewed_article_id(reviewed_path))
    return {
        "schema_version": SCHEMA_VERSION,
        "article_id": article_id,
        "status": "draft",
        "created_at": created_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        "manifest_path": relative_to(manifest_path, reviewed_path.parent),
        "reviewed_path": relative_to(reviewed_path, reviewed_path.parent),
        "article": {
            "title": (manifest.get("article") or {}).get("title"),
            "url": (manifest.get("article") or {}).get("url"),
            "platform": (manifest.get("article") or {}).get("platform"),
        },
    }


def relative_to(path: Path, base_dir: Path) -> str:
    return Path(os.path.relpath(path, base_dir)).as_posix()
