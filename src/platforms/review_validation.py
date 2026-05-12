from __future__ import annotations

from pathlib import Path
from typing import Any

from src.core.review_validation import ValidationIssue


def validate_platform_review_structure(
    reviewed_markdown: str,
    manifest_path: Path,
    manifest: dict[str, Any],
    report: dict[str, Any],
) -> list[ValidationIssue]:
    article = manifest.get("article") if isinstance(manifest.get("article"), dict) else {}
    platform = str(article.get("platform") or "").strip()
    if platform == "wechat_mp":
        from src.platforms.wechat_mp.review_validation import validate_review_structure

        return validate_review_structure(reviewed_markdown, manifest_path, manifest, report)
    return []
