"""Tests for review report readers."""
from __future__ import annotations

import json
from pathlib import Path

from src.core.review.review_report import read_review_ai_settings, review_report_path


def test_read_review_ai_settings_requires_complete_review(tmp_path: Path) -> None:
    reviewed_path = tmp_path / "reviewed.md"
    assert read_review_ai_settings(reviewed_path) is None
    for report in (
        [],
        {"status": "draft", "ai": {"rewrite_provider": "openai", "rewrite_model": "m"}},
        {"status": "reviewed", "ai": "invalid"},
        {"status": "reviewed", "ai": {"rewrite_provider": "openai"}},
    ):
        review_report_path(reviewed_path).write_text(json.dumps(report), encoding="utf-8")
        assert read_review_ai_settings(reviewed_path) is None


def test_read_review_ai_settings_returns_provenance(tmp_path: Path) -> None:
    reviewed_path = tmp_path / "reviewed.md"
    review_report_path(reviewed_path).write_text(
        json.dumps(
            {
                "status": "reviewed",
                "ai": {"rewrite_provider": "openai", "rewrite_model": "gpt-test"},
            }
        ),
        encoding="utf-8",
    )
    assert read_review_ai_settings(reviewed_path) == ("openai", "gpt-test")
