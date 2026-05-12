from __future__ import annotations

import json

import pytest

from src.core.review_report import inferred_manifest_path, review_report_path, write_review_report


def test_review_report_paths_are_inferred_from_reviewed_file(tmp_path):
    reviewed_path = tmp_path / "article" / "reviewed.md"

    assert inferred_manifest_path(reviewed_path) == tmp_path / "article" / "manifest.json"
    assert review_report_path(reviewed_path) == tmp_path / "article" / "review.json"


def test_write_review_report_creates_draft_schema(tmp_path):
    article_dir = tmp_path / "article"
    article_dir.mkdir(parents=True)
    reviewed_path = article_dir / "reviewed.md"
    manifest_path = article_dir / "manifest.json"
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

    assert report_path == article_dir / "review.json"
    assert report["schema_version"] == 1
    assert report["article_id"] == "article"
    assert report["manifest_path"] == "manifest.json"
    assert report["reviewed_path"] == "reviewed.md"
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
        "platform_noise_actions": [],
        "suggested_platform_markers": [],
    }


def test_write_review_report_refuses_to_overwrite_without_flag(tmp_path):
    article_dir = tmp_path / "article"
    article_dir.mkdir(parents=True)
    reviewed_path = article_dir / "reviewed.md"
    manifest_path = article_dir / "manifest.json"
    report_path = article_dir / "review.json"
    reviewed_path.write_text("# Reviewed\n", encoding="utf-8")
    manifest_path.write_text('{"article_id": "article", "article": {}}', encoding="utf-8")
    report_path.write_text('{"status": "edited"}', encoding="utf-8")

    with pytest.raises(ValueError, match="already exists"):
        write_review_report(reviewed_path)

    write_review_report(reviewed_path, overwrite=True)
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "draft"
