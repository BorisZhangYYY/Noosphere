"""Tests for CLI argument wiring."""
from __future__ import annotations

from src.cli import parse_args


def test_ai_review_accepts_perspective() -> None:
    args = parse_args(["ai-review", "article-id", "--perspective", "novice", "--language", "en-US"])

    assert args.perspective == "novice"
    assert args.language == "en-US"


def test_run_accepts_perspective() -> None:
    args = parse_args(["run", "https://example.com/article", "--perspective", "original", "--language", "zh-CN"])

    assert args.perspective == "original"
    assert args.language == "zh-CN"


def test_core_pipeline_commands_support_json_output() -> None:
    assert parse_args(["extract", "https://example.com", "--json"]).json is True
    assert parse_args(["ai-review", "article-id", "--json"]).json is True
    assert parse_args(["upload", "article-id", "--json"]).json is True
    assert parse_args(["run", "https://example.com", "--json"]).json is True


def test_taxonomy_move_accepts_stable_ids_and_localizations() -> None:
    args = parse_args([
        "taxonomy", "move", "article-id",
        "--tag-id", "tag-1",
        "--subtag-id", "subtag-1",
        "--tag-localizations", '{"en-US":{"name":"AI"},"zh-CN":{"name":"人工智能"}}',
        "--json",
    ])

    assert args.taxonomy_command == "move"
    assert args.tag_id == "tag-1"
    assert args.subtag_id == "subtag-1"
    assert args.json is True


def test_taxonomy_create_and_update_accept_management_fields() -> None:
    created = parse_args([
        "taxonomy", "create",
        "--name", "Engineering",
        "--description", "Software practices",
        "--parent-id", "root-1",
        "--locale", "en-US",
        "--json",
    ])
    updated = parse_args([
        "taxonomy", "update", "root-1",
        "--name", "软件工程",
        "--description", "软件实践",
        "--retire",
        "--locale", "zh-CN",
        "--json",
    ])

    assert created.taxonomy_command == "create"
    assert created.parent_id == "root-1"
    assert updated.taxonomy_command == "update"
    assert updated.retire is True
    assert updated.locale == "zh-CN"


def test_perspective_save_accepts_template_contract(tmp_path) -> None:
    prompt = tmp_path / "prompt.md"
    template = tmp_path / "template.md"
    prompt.write_text("Review carefully.", encoding="utf-8")
    template.write_text("# {{title}}\n\n{{source_metadata}}\n\n{{body}}", encoding="utf-8")

    args = parse_args([
        "perspectives", "save", "research",
        "--label", "Research",
        "--prompt-file", str(prompt),
        "--template-file", str(template),
        "--sections", '{"body":"Article"}',
        "--body-section", "body",
    ])

    assert args.perspectives_command == "save"
    assert args.perspective_id == "research"
    assert args.body_section == "body"


def test_config_reveal_requires_explicit_acknowledgement() -> None:
    args = parse_args(["config", "reveal", "ai"])

    assert args.yes is False
