from __future__ import annotations

import json
from pathlib import Path

from src.core.article_metadata import apply_ai_metadata_candidates, article_metadata_state


def _workspace(tmp_path: Path, *, author: str | None = None) -> tuple[Path, str]:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({
        "article_id": "article",
        "article": {
            "url": "https://example.com/article",
            "platform": "web",
            "platform_label": "Web",
            "title": "Article",
            "author": author,
            "published_at": None,
            "captured_at": "2026-07-27T00:00:00+00:00",
            "content_type": "article",
        },
        "paths": {"raw": "raw.md", "reviewed": "reviewed.md"},
    }), encoding="utf-8")
    raw = """# Article

> Source: [https://example.com/article](https://example.com/article)
> Platform: Web
> Captured: 2026-07-27T00:00:00+00:00
> Type: article

---

Written by Ada Lovelace for the July 27, 2026 edition.
"""
    return manifest_path, raw


def test_ai_metadata_enrichment_requires_verbatim_source_evidence(tmp_path: Path) -> None:
    manifest_path, raw = _workspace(tmp_path)
    reviewed, outcomes = apply_ai_metadata_candidates(
        manifest_path,
        raw,
        "# Improved article\n\nReviewed body.\n",
        {
            "author": {"value": "Ada Lovelace", "evidence": "Written by Ada Lovelace"},
            "publishedAt": {"value": "2026-07-27", "evidence": "July 27, 2026 edition"},
        },
        model="review-model",
        provider="provider",
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert [item["action"] for item in outcomes] == ["accepted", "accepted"]
    assert manifest["metadata_enrichment"]["fields"]["author"]["value"] == "Ada Lovelace"
    assert manifest["metadata_enrichment"]["fields"]["author"]["model"] == "review-model"
    assert "> Author: Ada Lovelace" in reviewed
    assert "> Published: 2026-07-27" in reviewed
    state = article_metadata_state(manifest, raw)
    assert state["author"]["origin"] == "ai"
    assert state["author"]["editable"] is False
    assert state["author"]["evidence"] == "Written by Ada Lovelace"


def test_ai_metadata_enrichment_reverts_unverifiable_or_replacement_candidates(tmp_path: Path) -> None:
    manifest_path, raw = _workspace(tmp_path)
    apply_ai_metadata_candidates(
        manifest_path,
        raw,
        "# Article\n\nBody.\n",
        {"author": {"value": "Ada Lovelace", "evidence": "Written by Ada Lovelace"}},
        model="first",
        provider="provider",
    )
    reviewed, outcomes = apply_ai_metadata_candidates(
        manifest_path,
        raw,
        "# Article\n\nBody.\n",
        {
            "author": {"value": "Grace Hopper", "evidence": "Written by Ada Lovelace"},
            "publishedAt": {"value": "2099-01-01", "evidence": "July 27, 2026 edition"},
        },
        model="second",
        provider="provider",
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert [item["action"] for item in outcomes] == ["reverted", "reverted"]
    assert manifest["metadata_enrichment"]["fields"]["author"]["value"] == "Ada Lovelace"
    assert "publishedAt" not in manifest["metadata_enrichment"]["fields"]
    assert "> Author: Ada Lovelace" in reviewed
    assert "> Published: Unknown" in reviewed


def test_ai_metadata_enrichment_never_overwrites_captured_values(tmp_path: Path) -> None:
    manifest_path, raw = _workspace(tmp_path, author="Captured Author")
    reviewed, outcomes = apply_ai_metadata_candidates(
        manifest_path,
        raw,
        "# Article\n\nBody.\n",
        {"author": {"value": "Ada Lovelace", "evidence": "Written by Ada Lovelace"}},
        model="review-model",
        provider="provider",
    )

    assert outcomes[0]["action"] == "reverted"
    assert "protected" in outcomes[0]["reason"]
    assert "> Author: Captured Author" in reviewed
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "author" not in manifest["metadata_enrichment"]["fields"]
