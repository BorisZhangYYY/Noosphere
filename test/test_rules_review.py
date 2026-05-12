from __future__ import annotations

import json

from src.core.rules_review import format_rules_review, review_platform_rules


def write_messy_rules(tmp_path):
    rules_dir = tmp_path / "platform_rules"
    rules_dir.mkdir()
    (rules_dir / "wechat_mp.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "platform": "wechat_mp",
                "markers": [
                    {"id": "a", "text": "关注该公众号", "category": "platform_footer"},
                    {"id": "b", "text": "关注该公众号", "category": "platform_footer"},
                    {"id": "a", "text": "重复ID", "category": "platform_ui"},
                    {"id": "c", "text": "", "category": "platform_ui"},
                    {"id": "d", "text": "go", "category": "promotion"},
                    {"id": "e", "text": "之前写过一篇", "category": "interaction_prompt"},
                    {
                        "id": "f",
                        "text": "之前写过一篇...录友们可以连着看",
                        "category": "made_up",
                    },
                ],
                "non_topic_headings": ["AI Summary"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return rules_dir


def test_rules_review_reports_duplicates_short_markers_and_overlaps(tmp_path):
    rules_dir = write_messy_rules(tmp_path)

    result = review_platform_rules("wechat_mp", rules_dir=rules_dir)
    codes = {issue.code for issue in result.issues}
    report = format_rules_review(result)

    assert result.marker_count == 7
    assert result.final_marker_count == 6
    assert "duplicate_text" in codes
    assert "duplicate_id" in codes
    assert "empty_text" in codes
    assert "short_marker" in codes
    assert "invalid_category" in codes
    assert "substring_overlap" in codes
    assert "Rules review: wechat_mp" in report
    assert "Action: manual review" in report


def test_rules_review_apply_only_safe_cleanup(tmp_path):
    rules_dir = write_messy_rules(tmp_path)

    result = review_platform_rules("wechat_mp", rules_dir=rules_dir, apply=True)
    data = json.loads((rules_dir / "wechat_mp.json").read_text(encoding="utf-8"))
    markers = data["markers"]

    assert result.applied is True
    assert result.marker_count == 7
    assert result.final_marker_count == 4
    assert result.removed_count == 3
    assert result.normalized_count == 1
    assert [marker["text"] for marker in markers] == [
        "关注该公众号",
        "go",
        "之前写过一篇",
        "之前写过一篇...录友们可以连着看",
    ]
    assert markers[-1]["category"] == "platform_ui"


def test_rules_review_falls_back_to_example_and_apply_writes_local_copy(tmp_path):
    rules_dir = tmp_path / "platform_rules"
    example_rules_dir = tmp_path / "platform_rules.example"
    example_rules_dir.mkdir()
    (example_rules_dir / "wechat_mp.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "platform": "wechat_mp",
                "markers": [
                    {"id": "example", "text": "关注该公众号", "category": "platform_footer"},
                    {"id": "duplicate", "text": "关注该公众号", "category": "platform_footer"},
                ],
                "non_topic_headings": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = review_platform_rules("wechat_mp", rules_dir=rules_dir, example_rules_dir=example_rules_dir, apply=True)

    assert result.source_path == example_rules_dir / "wechat_mp.json"
    assert result.output_path == rules_dir / "wechat_mp.json"
    assert result.removed_count == 1
    assert result.output_path.exists()
