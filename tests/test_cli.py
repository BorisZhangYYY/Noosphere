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
    assert parse_args(["reflect", "article-id", "--json"]).json is True


def test_reflect_command_and_persistent_upload_preference() -> None:
    args = parse_args([
        "reflect",
        "article-id",
        "--set",
        "我的感悟。",
        "--polish",
        "--apply",
        "--upload-enabled",
    ])
    assert args.set_text == "我的感悟。"
    assert args.polish is True
    assert args.apply is True
    assert args.upload_enabled is True
    assert parse_args(["reflect", "article-id", "--no-upload-enabled"]).upload_enabled is False


def test_upload_accepts_reflection_override() -> None:
    assert parse_args(["upload", "article-id", "--include-reflection"]).include_reflection is True
    assert parse_args(["upload", "article-id", "--no-include-reflection"]).include_reflection is False
    assert parse_args(["upload", "article-id"]).include_reflection is None


def test_article_metadata_command_accepts_only_enrichable_fields() -> None:
    args = parse_args([
        "articles", "metadata", "article-id",
        "--author", "Verified author",
        "--published-at", "2026-07-02",
        "--json",
    ])

    assert args.articles_command == "metadata"
    assert args.author == "Verified author"
    assert args.published_at == "2026-07-02"


def test_collection_move_accepts_stable_id() -> None:
    args = parse_args([
        "collections", "move", "article-id",
        "--collection-id", "collection-1",
        "--json",
    ])

    assert args.collections_command == "move"
    assert args.collection_id == "collection-1"
    assert args.json is True


def test_collection_move_accepts_explicit_missing_leaf_creation() -> None:
    args = parse_args([
        "collections", "place", "article-id",
        "--collection-path", "AI 相关 / AI 测评",
        "--create-missing",
        "--description", "模型能力、基准与真实使用体验的评估内容。",
        "--json",
    ])

    assert args.collection_path == "AI 相关 / AI 测评"
    assert args.create_missing is True
    assert args.description == "模型能力、基准与真实使用体验的评估内容。"


def test_collection_create_and_update_accept_management_fields() -> None:
    created = parse_args([
        "collections", "create",
        "--name", "Engineering",
        "--description", "Software practices",
        "--parent-id", "root-1",
        "--json",
    ])
    updated = parse_args([
        "collections", "update", "root-1",
        "--name", "软件工程",
        "--description", "软件实践",
        "--retire",
        "--json",
    ])

    assert created.collections_command == "create"
    assert created.parent_id == "root-1"
    assert updated.collections_command == "update"
    assert updated.retire is True


def test_collection_delete_and_restore_are_explicit_commands() -> None:
    deleted = parse_args(["collections", "delete", "root-1", "--json"])
    restored = parse_args(["collections", "restore", "root-1", "--json"])

    assert deleted.collections_command == "delete"
    assert deleted.collection_id == "root-1"
    assert deleted.json is True
    assert restored.collections_command == "restore"
    assert restored.collection_id == "root-1"


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
