from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1


def inferred_manifest_path(reviewed_path: Path) -> Path:
    return reviewed_path.parent.parent / "manifests" / f"{reviewed_path.stem}.json"


def review_report_path(reviewed_path: Path) -> Path:
    return reviewed_path.parent.parent / "reviews" / f"{reviewed_path.stem}.json"


def build_review_report(
    reviewed_path: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
    created_at: str | None = None,
) -> dict[str, Any]:
    article_id = str(manifest.get("article_id") or reviewed_path.stem)
    output_dir = reviewed_path.parent.parent
    return {
        "schema_version": SCHEMA_VERSION,
        "article_id": article_id,
        "status": "draft",
        "created_at": created_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        "manifest_path": relative_to(manifest_path, output_dir),
        "reviewed_path": relative_to(reviewed_path, output_dir),
        "article": {
            "title": (manifest.get("article") or {}).get("title"),
            "url": (manifest.get("article") or {}).get("url"),
            "platform": (manifest.get("article") or {}).get("platform"),
        },
        "review": {
            "summary": "",
            "removed_noise": [],
            "preserved_sections": [],
            "formatting_changes": [],
            "image_decisions": [],
            "suggested_rule_candidates": [],
        },
    }


def write_review_report(
    reviewed_path: Path,
    manifest_path: Path | None = None,
    overwrite: bool = False,
) -> Path:
    resolved_manifest_path = manifest_path or inferred_manifest_path(reviewed_path)
    if not reviewed_path.exists():
        raise ValueError(f"Reviewed Markdown file not found: {reviewed_path}")
    if not resolved_manifest_path.exists():
        raise ValueError(f"Extraction manifest not found: {resolved_manifest_path}")

    output_path = review_report_path(reviewed_path)
    if output_path.exists() and not overwrite:
        raise ValueError(f"Review report already exists: {output_path}")

    manifest = json.loads(resolved_manifest_path.read_text(encoding="utf-8"))
    report = build_review_report(reviewed_path, resolved_manifest_path, manifest)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def relative_to(path: Path, base_dir: Path) -> str:
    return Path(os.path.relpath(path, base_dir)).as_posix()
