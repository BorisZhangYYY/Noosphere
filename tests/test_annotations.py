"""Tests for durable quoted-passage annotations."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from src.core.annotations import (
    create_annotation,
    delete_annotation,
    read_annotations,
    reviewed_digest,
    update_annotation,
)


def _create(article_dir: Path, index: int = 0) -> dict:
    return create_annotation(
        article_dir,
        quote=f"Passage {index}",
        prefix="Before ",
        suffix=" after",
        occurrence=index,
        note=f"**Meaning {index}**",
        source_digest=reviewed_digest("# Article\n"),
    )


def test_annotation_lifecycle_preserves_anchor(tmp_path: Path) -> None:
    article_dir = tmp_path / "article"
    created = _create(article_dir)

    assert read_annotations(article_dir) == [created]
    updated = update_annotation(article_dir, created["id"], note="## Updated")
    assert updated["quote"] == created["quote"]
    assert updated["source_digest"] == created["source_digest"]
    assert updated["note"] == "## Updated"
    assert updated["updated_at"] >= created["updated_at"]

    removed = delete_annotation(article_dir, created["id"])
    assert removed["id"] == created["id"]
    assert read_annotations(article_dir) == []


def test_annotation_writes_are_serialized(tmp_path: Path) -> None:
    article_dir = tmp_path / "article"
    with ThreadPoolExecutor(max_workers=8) as pool:
        created = list(pool.map(lambda index: _create(article_dir, index), range(24)))

    stored = read_annotations(article_dir)
    assert len(stored) == 24
    assert {item["id"] for item in stored} == {item["id"] for item in created}


def test_corrupt_annotation_document_is_never_overwritten(tmp_path: Path) -> None:
    article_dir = tmp_path / "article"
    article_dir.mkdir()
    path = article_dir / "annotations.json"
    path.write_text("{not valid", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid"):
        _create(article_dir)
    assert path.read_text(encoding="utf-8") == "{not valid"


@pytest.mark.parametrize("digest", ["x" * 64, "0" * 63, "A" * 64])
def test_annotation_rejects_invalid_source_digest(tmp_path: Path, digest: str) -> None:
    with pytest.raises(ValueError, match="source_digest"):
        create_annotation(
            tmp_path,
            quote="Passage",
            prefix="",
            suffix="",
            occurrence=0,
            note="Meaning",
            source_digest=digest,
        )


def test_annotation_service_uses_reviewed_digest_without_touching_article_files(monkeypatch, tmp_path: Path) -> None:
    article_dir = tmp_path / "article"
    article_dir.mkdir()
    original = {
        "raw.md": "# Raw\n",
        "reviewed.md": "# Reviewed\n\nPassage.\n",
        "reflection.md": "Reflection.\n",
        "manifest.json": json.dumps({"article_id": "article"}),
    }
    for name, content in original.items():
        (article_dir / name).write_text(content, encoding="utf-8")
    monkeypatch.setattr("src.api.web._safe_article_dir", lambda article_id: article_dir)

    from src.application.service import create_article_annotation, get_article_annotations

    created = create_article_annotation("article", quote="Passage.", note="Meaning")
    result = get_article_annotations("article")

    assert created["sourceDigest"] == reviewed_digest(original["reviewed.md"])
    assert result["count"] == 1
    assert result["items"][0] == created
    for name, content in original.items():
        assert (article_dir / name).read_text(encoding="utf-8") == content
