"""Per-article reflection storage and upload composition."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from src.core.localization import normalize_language


REFLECTION_FILENAME = "reflection.md"
REFLECTION_HEADINGS = {
    "en-US": "## My Reflections",
    "zh-CN": "## 我的感悟",
}


def reflection_heading(language: str) -> str:
    """Return the canonical reflection heading for a supported language."""
    return REFLECTION_HEADINGS[normalize_language(language, default="en-US")]


def read_reflection(article_dir: Path) -> str:
    """Return reflection Markdown, or an empty string when it is absent."""
    path = Path(article_dir) / REFLECTION_FILENAME
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _atomic_write_text(path: Path, content: str) -> None:
    """Write text atomically with a unique sibling temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def write_reflection(article_dir: Path, markdown: str) -> Path:
    """Atomically write reflection Markdown and return its path."""
    path = Path(article_dir) / REFLECTION_FILENAME
    _atomic_write_text(path, markdown)
    return path


def _read_manifest(manifest_path: Path) -> dict[str, Any]:
    """Read a valid article manifest without replacing damaged metadata."""
    if not manifest_path.is_file():
        raise ValueError(f"Article manifest not found: {manifest_path}")
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Article manifest is invalid: {manifest_path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Article manifest is invalid: {manifest_path}")
    return value


def read_upload_enabled(manifest_path: Path) -> bool:
    """Return whether uploads should append the reflection section."""
    try:
        manifest = _read_manifest(Path(manifest_path))
    except ValueError:
        return False
    reflection = manifest.get("reflection")
    return bool(reflection.get("upload_enabled")) if isinstance(reflection, dict) else False


def set_upload_enabled(manifest_path: Path, enabled: bool) -> None:
    """Persist the upload toggle without discarding manifest metadata."""
    manifest_path = Path(manifest_path)
    manifest = _read_manifest(manifest_path)
    reflection = manifest.get("reflection")
    if not isinstance(reflection, dict):
        reflection = {}
        manifest["reflection"] = reflection
    reflection["upload_enabled"] = bool(enabled)
    _atomic_write_text(
        manifest_path,
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
    )


def merge_reflection(
    reviewed_markdown: str,
    reflection_markdown: str,
    language: str = "en-US",
) -> str:
    """Append a localized reflection section to reviewed Markdown."""
    reflection = reflection_markdown.strip()
    if not reflection:
        return reviewed_markdown
    return (
        f"{reviewed_markdown.rstrip()}\n\n---\n\n"
        f"{reflection_heading(language)}\n\n{reflection}\n"
    )
