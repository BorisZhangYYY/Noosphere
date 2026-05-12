from __future__ import annotations

import json

from src.core.platform_rules import (
    append_suggested_platform_markers,
    detect_noise_hints,
    format_noise_hints_context,
    load_platform_rules,
    normalize_marker_category,
    write_noise_hints,
)
from src.platforms.wechat_mp.cleaning import clean as clean_wechat
from src.platforms.zhihu_zhuanlan.cleaning import clean as clean_zhihu


def write_rules(tmp_path):
    rules_dir = tmp_path / "platform_rules"
    rules_dir.mkdir()
    (rules_dir / "wechat_mp.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "platform": "wechat_mp",
                "markers": [
                    {
                        "id": "wechat_mp.platform_footer.follow_account",
                        "text": "关注该公众号",
                        "category": "platform_footer",
                    }
                ],
                "non_topic_headings": ["AI Summary"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return rules_dir


def write_example_rules(tmp_path):
    example_rules_dir = tmp_path / "platform_rules.example"
    example_rules_dir.mkdir()
    (example_rules_dir / "wechat_mp.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "platform": "wechat_mp",
                "markers": [
                    {
                        "id": "wechat_mp.example.follow_account",
                        "text": "关注该公众号",
                        "category": "platform_footer",
                    }
                ],
                "non_topic_headings": ["AI Summary"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return example_rules_dir


def test_platform_cleaning_no_longer_deletes_matched_content():
    markdown = "正文第一段\n\n关注该公众号\n\n后续正文"
    zhihu_markdown = "[link](https://example.com/a?zd_token=abc&x=1)"

    assert clean_wechat(markdown, "Title") == markdown
    assert clean_zhihu(zhihu_markdown, "Title") == zhihu_markdown


def test_detect_noise_hints_reports_marker_hits(tmp_path):
    rules_dir = write_rules(tmp_path)
    hints = detect_noise_hints("正文\n关注该公众号\n正文", "wechat_mp", rules_dir)

    assert hints["hints"] == [
        {
            "hint_id": "wechat_mp.platform_footer.follow_account",
            "marker": "关注该公众号",
            "category": "platform_footer",
            "line": 2,
            "snippet": "关注该公众号",
        }
    ]


def test_format_noise_hints_context_uses_fixed_english_prompt():
    context = format_noise_hints_context(
        {
            "schema_version": 1,
            "platform": "wechat_mp",
            "hints": [
                {
                    "hint_id": "wechat_mp.platform_footer.follow_account",
                    "marker": "关注该公众号",
                    "category": "platform_footer",
                    "line": 2,
                    "snippet": "关注该公众号",
                }
            ],
        }
    )

    assert "Platform noise hints:" in context
    assert "[wechat_mp.platform_footer.follow_account] line 2 hit marker \"关注该公众号\"" in context
    assert "possible platform noise, needs review" in context


def test_write_noise_hints_creates_article_sidecar(tmp_path):
    rules_dir = write_rules(tmp_path)
    path = tmp_path / "article" / "noise_hints.json"

    write_noise_hints(path, "正文\n关注该公众号\n正文", "wechat_mp", rules_dir)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["platform"] == "wechat_mp"
    assert data["hints"][0]["line"] == 2


def test_append_suggested_platform_markers_writes_short_rules(tmp_path):
    rules_dir = write_rules(tmp_path)

    appended = append_suggested_platform_markers(
        "wechat_mp",
        [
            {
                "text": "顺手关注一下",
                "category": "interaction_prompt",
                "reason": "常见文末关注提示。",
            },
            {
                "text": "关注该公众号",
                "category": "platform_footer",
                "reason": "已存在。",
            },
        ],
        rules_dir,
    )

    rules = load_platform_rules("wechat_mp", rules_dir)
    assert appended == [
        {
            "id": appended[0]["id"],
            "text": "顺手关注一下",
            "category": "interaction_prompt",
        }
    ]
    assert {marker["text"] for marker in rules["markers"]} == {"关注该公众号", "顺手关注一下"}


def test_marker_category_is_limited_to_known_values(tmp_path):
    rules_dir = tmp_path / "platform_rules"
    rules_dir.mkdir()
    (rules_dir / "wechat_mp.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "platform": "wechat_mp",
                "markers": [
                    {
                        "id": "known",
                        "text": "顺手关注一下",
                        "category": "interaction_prompt",
                    },
                    {
                        "id": "unknown",
                        "text": "奇怪分类",
                        "category": "made_up_category",
                    },
                ],
                "non_topic_headings": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rules = load_platform_rules("wechat_mp", rules_dir)

    assert rules["markers"][0]["category"] == "interaction_prompt"
    assert rules["markers"][1]["category"] == "platform_ui"
    assert normalize_marker_category("promotion") == "promotion"
    assert normalize_marker_category("bad") == "platform_ui"


def test_append_suggested_platform_markers_normalizes_unknown_category(tmp_path):
    rules_dir = write_rules(tmp_path)

    appended = append_suggested_platform_markers(
        "wechat_mp",
        [{"text": "新号", "category": "new_account", "reason": "AI invented category."}],
        rules_dir,
    )

    assert appended[0]["category"] == "platform_ui"
    assert load_platform_rules("wechat_mp", rules_dir)["markers"][-1]["category"] == "platform_ui"


def test_load_platform_rules_falls_back_to_example_rules(tmp_path):
    rules_dir = tmp_path / "platform_rules"
    example_rules_dir = write_example_rules(tmp_path)

    rules = load_platform_rules("wechat_mp", rules_dir, example_rules_dir)

    assert rules["markers"][0]["id"] == "wechat_mp.example.follow_account"
    assert rules["non_topic_headings"] == ["AI Summary"]


def test_append_suggested_platform_markers_creates_local_rules_from_example(tmp_path):
    rules_dir = tmp_path / "platform_rules"
    example_rules_dir = write_example_rules(tmp_path)

    appended = append_suggested_platform_markers(
        "wechat_mp",
        [{"text": "顺手关注一下", "category": "interaction_prompt", "reason": "AI suggestion."}],
        rules_dir,
        example_rules_dir,
    )

    rules_path = rules_dir / "wechat_mp.json"
    assert rules_path.exists()
    assert appended[0]["text"] == "顺手关注一下"
    assert {marker["text"] for marker in load_platform_rules("wechat_mp", rules_dir, example_rules_dir)["markers"]} == {
        "关注该公众号",
        "顺手关注一下",
    }
