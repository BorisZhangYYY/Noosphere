from __future__ import annotations

import json

import pytest

from src.core.review_report import inferred_manifest_path, review_report_path, write_review_report


def test_review_report_paths_are_inferred_from_reviewed_file(tmp_path):
    reviewed_path = tmp_path / "reviewed" / "article.md"

    assert inferred_manifest_path(reviewed_path) == tmp_path / "manifests" / "article.json"
    assert review_report_path(reviewed_path) == tmp_path / "reviews" / "article.json"


def test_write_review_report_creates_draft_schema(tmp_path):
    reviewed_dir = tmp_path / "reviewed"
    manifest_dir = tmp_path / "manifests"
    reviewed_dir.mkdir()
    manifest_dir.mkdir()
    reviewed_path = reviewed_dir / "article.md"
    manifest_path = manifest_dir / "article.json"
    reviewed_path.write_text("# Reviewed\n\nBody\n", encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "article_id": "article",
                "article": {
                    "title": "Article Title",
                    "url": "https://example.com/article",
                    "platform": "wechat_mp",
                },
            }
        ),
        encoding="utf-8",
    )

    report_path = write_review_report(reviewed_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report_path == tmp_path / "reviews" / "article.json"
    assert report["schema_version"] == 1
    assert report["article_id"] == "article"
    assert report["manifest_path"] == "manifests/article.json"
    assert report["reviewed_path"] == "reviewed/article.md"
    assert report["article"] == {
        "title": "Article Title",
        "url": "https://example.com/article",
        "platform": "wechat_mp",
    }
    assert report["review"] == {
        "summary": "",
        "removed_noise": [],
        "preserved_sections": [],
        "formatting_changes": [],
        "image_decisions": [],
        "suggested_rule_candidates": [],
    }


def test_write_review_report_refuses_to_overwrite_without_flag(tmp_path):
    reviewed_dir = tmp_path / "reviewed"
    manifest_dir = tmp_path / "manifests"
    review_dir = tmp_path / "reviews"
    reviewed_dir.mkdir()
    manifest_dir.mkdir()
    review_dir.mkdir()
    reviewed_path = reviewed_dir / "article.md"
    manifest_path = manifest_dir / "article.json"
    report_path = review_dir / "article.json"
    reviewed_path.write_text("# Reviewed\n", encoding="utf-8")
    manifest_path.write_text('{"article_id": "article", "article": {}}', encoding="utf-8")
    report_path.write_text('{"status": "edited"}', encoding="utf-8")

    with pytest.raises(ValueError, match="already exists"):
        write_review_report(reviewed_path)

    write_review_report(reviewed_path, overwrite=True)
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "draft"
