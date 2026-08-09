"""Durable quote annotations stored beside an article workspace."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator


ANNOTATIONS_FILENAME = "annotations.json"
ANNOTATIONS_VERSION = 1
MAX_QUOTE_BYTES = 16 * 1024
MAX_CONTEXT_BYTES = 4 * 1024
MAX_NOTE_BYTES = 2 * 1024 * 1024


def reviewed_digest(reviewed_markdown: str) -> str:
    """Return the stable digest used to detect source changes."""
    return hashlib.sha256(reviewed_markdown.encode("utf-8")).hexdigest()


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


@contextmanager
def _workspace_lock(article_dir: Path) -> Iterator[None]:
    lock_path = article_dir / ".annotations.lock"
    article_dir.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _validate_annotation(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Article annotations are invalid")
    required_strings = (
        "id",
        "quote",
        "prefix",
        "suffix",
        "note",
        "source_digest",
        "created_at",
        "updated_at",
    )
    if any(not isinstance(value.get(key), str) for key in required_strings):
        raise ValueError("Article annotations are invalid")
    occurrence = value.get("occurrence")
    if not isinstance(occurrence, int) or isinstance(occurrence, bool) or occurrence < 0:
        raise ValueError("Article annotations are invalid")
    if not value["id"].strip() or not value["quote"].strip() or not value["note"].strip():
        raise ValueError("Article annotations are invalid")
    if len(value["id"].encode("utf-8")) > 256:
        raise ValueError("Article annotations are invalid")
    if len(value["quote"].encode("utf-8")) > MAX_QUOTE_BYTES:
        raise ValueError("Article annotations are invalid")
    if len(value["prefix"].encode("utf-8")) > MAX_CONTEXT_BYTES or len(value["suffix"].encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise ValueError("Article annotations are invalid")
    if len(value["note"].encode("utf-8")) > MAX_NOTE_BYTES:
        raise ValueError("Article annotations are invalid")
    if (
        len(value["source_digest"]) != 64
        or any(character not in "0123456789abcdef" for character in value["source_digest"])
    ):
        raise ValueError("Article annotations are invalid")
    return {
        "id": value["id"],
        "quote": value["quote"],
        "prefix": value["prefix"],
        "suffix": value["suffix"],
        "occurrence": occurrence,
        "note": value["note"],
        "source_digest": value["source_digest"],
        "created_at": value["created_at"],
        "updated_at": value["updated_at"],
    }


def _read_document(article_dir: Path) -> dict[str, Any]:
    path = article_dir / ANNOTATIONS_FILENAME
    if not path.is_file():
        return {"version": ANNOTATIONS_VERSION, "annotations": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Article annotations are invalid: {path}") from exc
    if not isinstance(value, dict) or value.get("version") != ANNOTATIONS_VERSION:
        raise ValueError(f"Article annotations are invalid: {path}")
    items = value.get("annotations")
    if not isinstance(items, list):
        raise ValueError(f"Article annotations are invalid: {path}")
    try:
        annotations = [_validate_annotation(item) for item in items]
    except ValueError as exc:
        raise ValueError(f"Article annotations are invalid: {path}") from exc
    ids = [item["id"] for item in annotations]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Article annotations are invalid: {path}")
    return {"version": ANNOTATIONS_VERSION, "annotations": annotations}


def read_annotations(article_dir: Path) -> list[dict[str, Any]]:
    """Return validated annotations, newest first."""
    document = _read_document(Path(article_dir))
    return sorted(
        document["annotations"],
        key=lambda item: (item["created_at"], item["id"]),
        reverse=True,
    )


def _bounded_text(value: Any, field: str, *, maximum_bytes: int, required: bool) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    normalized = value.strip() if required else value
    if required and not normalized:
        raise ValueError(f"{field} cannot be empty")
    if len(normalized.encode("utf-8")) > maximum_bytes:
        raise ValueError(f"{field} is too large")
    return normalized


def create_annotation(
    article_dir: Path,
    *,
    quote: str,
    prefix: str,
    suffix: str,
    occurrence: int,
    note: str,
    source_digest: str,
) -> dict[str, Any]:
    """Create one quote annotation with an immutable source anchor."""
    article_dir = Path(article_dir)
    normalized_quote = _bounded_text(quote, "quote", maximum_bytes=MAX_QUOTE_BYTES, required=True)
    normalized_prefix = _bounded_text(prefix, "prefix", maximum_bytes=MAX_CONTEXT_BYTES, required=False)
    normalized_suffix = _bounded_text(suffix, "suffix", maximum_bytes=MAX_CONTEXT_BYTES, required=False)
    normalized_note = _bounded_text(note, "note", maximum_bytes=MAX_NOTE_BYTES, required=True)
    if not isinstance(occurrence, int) or isinstance(occurrence, bool) or occurrence < 0:
        raise ValueError("occurrence must be a non-negative integer")
    if (
        not isinstance(source_digest, str)
        or len(source_digest) != 64
        or any(character not in "0123456789abcdef" for character in source_digest)
    ):
        raise ValueError("source_digest is invalid")
    now = datetime.now(UTC).isoformat()
    annotation = {
        "id": uuid.uuid4().hex,
        "quote": normalized_quote,
        "prefix": normalized_prefix,
        "suffix": normalized_suffix,
        "occurrence": occurrence,
        "note": normalized_note,
        "source_digest": source_digest,
        "created_at": now,
        "updated_at": now,
    }
    with _workspace_lock(article_dir):
        document = _read_document(article_dir)
        document["annotations"].append(annotation)
        _atomic_write_json(article_dir / ANNOTATIONS_FILENAME, document)
    return annotation


def update_annotation(article_dir: Path, annotation_id: str, *, note: str) -> dict[str, Any]:
    """Update only the reader-authored Markdown interpretation."""
    article_dir = Path(article_dir)
    normalized_id = _bounded_text(annotation_id, "annotation_id", maximum_bytes=256, required=True)
    normalized_note = _bounded_text(note, "note", maximum_bytes=MAX_NOTE_BYTES, required=True)
    with _workspace_lock(article_dir):
        document = _read_document(article_dir)
        for annotation in document["annotations"]:
            if annotation["id"] != normalized_id:
                continue
            annotation["note"] = normalized_note
            annotation["updated_at"] = datetime.now(UTC).isoformat()
            _atomic_write_json(article_dir / ANNOTATIONS_FILENAME, document)
            return annotation
    raise ValueError(f"Annotation not found: {normalized_id}")


def delete_annotation(article_dir: Path, annotation_id: str) -> dict[str, Any]:
    """Delete one annotation and return the removed record."""
    article_dir = Path(article_dir)
    normalized_id = _bounded_text(annotation_id, "annotation_id", maximum_bytes=256, required=True)
    with _workspace_lock(article_dir):
        document = _read_document(article_dir)
        for index, annotation in enumerate(document["annotations"]):
            if annotation["id"] != normalized_id:
                continue
            removed = document["annotations"].pop(index)
            _atomic_write_json(article_dir / ANNOTATIONS_FILENAME, document)
            return removed
    raise ValueError(f"Annotation not found: {normalized_id}")
