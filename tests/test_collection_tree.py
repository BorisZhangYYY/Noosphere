"""Tests for hierarchical collections and closed-set article placement."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.config.config import clear_config_cache


@pytest.fixture
def collection_store(monkeypatch, tmp_path: Path):
    runtime_home = tmp_path / ".noosphere"
    config_path = runtime_home / "config.json"
    runtime_home.mkdir()
    config_path.write_text(
        json.dumps({
            "output_dir": str(runtime_home / "articles"),
            "checkpoint": {"backend": "sqlite"},
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("NOOSPHERE_HOME", str(runtime_home))
    monkeypatch.setenv("NOOSPHERE_CONFIG", str(config_path))
    clear_config_cache()
    from src.core.collections import CollectionStore

    yield CollectionStore()
    clear_config_cache()


def test_new_workspace_starts_at_collection_root(collection_store) -> None:
    assert collection_store.list_tree() == []
    root = collection_store.assign_article("article", collection_id=None)
    assert root["collection_id"] is None
    assert root["collection_path"] == []


def test_collections_support_arbitrary_depth_and_article_counts(collection_store) -> None:
    ai = collection_store.create_collection(name="AI")
    interviews = collection_store.create_collection(name="AI Interviews", parent_id=ai["id"])
    agents = collection_store.create_collection(name="Coding Agents", parent_id=interviews["id"])
    research = collection_store.create_collection(name="Agent Evaluation", parent_id=agents["id"])

    placement = collection_store.assign_article(
        "article",
        collection_id=research["id"],
    )

    assert [item["name"] for item in placement["collection_path"]] == [
        "AI",
        "AI Interviews",
        "Coding Agents",
        "Agent Evaluation",
    ]
    tree = collection_store.list_tree()
    assert tree[0]["article_count"] == 1
    assert tree[0]["children"][0]["children"][0]["children"][0]["direct_article_count"] == 1


def test_collection_names_are_unique_only_among_siblings(collection_store) -> None:
    ai = collection_store.create_collection(name="AI")
    career = collection_store.create_collection(name="Career")
    collection_store.create_collection(name="Interviews", parent_id=ai["id"])
    collection_store.create_collection(name="Interviews", parent_id=career["id"])

    with pytest.raises(ValueError, match="already exists"):
        collection_store.create_collection(name="ai")


def test_collection_path_resolution_is_exact_and_case_insensitive(collection_store) -> None:
    ai = collection_store.create_collection(name="AI 相关")
    evaluation = collection_store.create_collection(
        name="AI 测评",
        description="模型能力与产品体验评估",
        parent_id=ai["id"],
    )

    resolved = collection_store.get_collection_by_path(["ai 相关", "ai 测评"])

    assert resolved is not None
    assert resolved["id"] == evaluation["id"]
    assert collection_store.get_collection_by_path(["AI 相关", "不存在"]) is None


def test_delete_and_restore_operate_on_the_complete_subtree(collection_store) -> None:
    ai = collection_store.create_collection(name="AI")
    interviews = collection_store.create_collection(name="Interviews", parent_id=ai["id"])
    deep = collection_store.create_collection(name="Systems", parent_id=interviews["id"])
    collection_store.assign_article("article", collection_id=deep["id"])

    deleted = collection_store.update_collection(ai["id"], retired=True)
    assert deleted["retired"] is True
    assert collection_store.list_tree() == []
    hidden = collection_store.get_assignment("article")
    assert hidden is not None
    assert hidden["collection_id"] is None

    collection_store.update_collection(ai["id"], retired=False)
    restored = collection_store.get_assignment("article")
    assert restored is not None
    assert restored["collection_id"] == deep["id"]
    assert [item["name"] for item in restored["collection_path"]] == ["AI", "Interviews", "Systems"]


def test_existing_two_level_taxonomy_migrates_without_losing_assignments(
    collection_store,
) -> None:
    database = collection_store._sqlite_path
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE noosphere_tags (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                parent_id TEXT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE noosphere_tag_states (
                tag_id TEXT PRIMARY KEY,
                retired_at TEXT NULL
            );
            CREATE TABLE noosphere_tag_localizations (
                tag_id TEXT NOT NULL,
                locale TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                aliases_json TEXT NOT NULL DEFAULT '[]',
                PRIMARY KEY(tag_id, locale)
            );
            CREATE TABLE noosphere_article_tags (
                article_id TEXT PRIMARY KEY,
                tag_id TEXT NOT NULL,
                subtag_id TEXT NULL,
                reason TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE noosphere_article_classification_details (
                article_id TEXT PRIMARY KEY,
                confidence REAL NOT NULL DEFAULT 1,
                source TEXT NOT NULL DEFAULT 'manual'
            );
            """
        )
        connection.execute(
            "INSERT INTO noosphere_tags VALUES (?, ?, ?, ?, ?)",
            ("ai", "AI", "", None, "2026-01-01T00:00:00+00:00"),
        )
        connection.execute(
            "INSERT INTO noosphere_tags VALUES (?, ?, ?, ?, ?)",
            ("interviews", "AI Interviews", "", "ai", "2026-01-01T00:00:00+00:00"),
        )
        connection.execute(
            "INSERT INTO noosphere_tag_localizations VALUES (?, ?, ?, ?, ?)",
            ("ai", "zh-CN", "AI 相关", "人工智能主题", "[]"),
        )
        connection.execute(
            "INSERT INTO noosphere_tag_localizations VALUES (?, ?, ?, ?, ?)",
            ("interviews", "zh-CN", "AI 面试", "面试与备考", "[]"),
        )
        connection.execute(
            "INSERT INTO noosphere_article_tags VALUES (?, ?, ?, ?, ?)",
            ("article", "ai", "interviews", "Legacy placement", "2026-01-01T00:00:00+00:00"),
        )
        connection.execute(
            "INSERT INTO noosphere_article_classification_details VALUES (?, ?, ?)",
            ("article", 0.91, "ai"),
        )

    assert [item["name"] for item in collection_store.list_tree()] == ["AI"]
    localized_tree = collection_store.list_tree(locale="zh-CN")
    assert localized_tree[0]["name"] == "AI 相关"
    assert localized_tree[0]["description"] == "人工智能主题"
    assert localized_tree[0]["children"][0]["name"] == "AI 面试"
    collection_store.update_collection(
        "ai",
        name="人工智能",
        locale="zh-CN",
    )
    assert collection_store.list_tree(locale="zh-CN")[0]["name"] == "人工智能"
    assert collection_store.list_tree(locale="en-US")[0]["name"] == "AI"
    placement = collection_store.get_assignment("article")
    assert placement is not None
    assert placement["collection_id"] == "interviews"
    assert [item["name"] for item in placement["collection_path"]] == ["AI", "AI Interviews"]
    assert placement["confidence"] == pytest.approx(0.91)


def test_localizations_are_backfilled_for_workspaces_already_migrated(
    collection_store,
) -> None:
    database = collection_store._sqlite_path
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE noosphere_collections (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                parent_id TEXT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE noosphere_collection_migrations (
                migration_key TEXT PRIMARY KEY,
                migrated_at TEXT NOT NULL
            );
            CREATE TABLE noosphere_tag_localizations (
                tag_id TEXT NOT NULL,
                locale TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                aliases_json TEXT NOT NULL DEFAULT '[]',
                PRIMARY KEY(tag_id, locale)
            );
            """
        )
        connection.execute(
            "INSERT INTO noosphere_collections VALUES (?, ?, ?, ?, ?)",
            ("ai", "AI", "Artificial intelligence", None, "2026-01-01T00:00:00+00:00"),
        )
        connection.execute(
            "INSERT INTO noosphere_collection_migrations VALUES (?, ?)",
            ("taxonomy-v1-to-collections-v1", "2026-01-01T00:00:00+00:00"),
        )
        connection.execute(
            "INSERT INTO noosphere_tag_localizations VALUES (?, ?, ?, ?, ?)",
            ("ai", "zh-CN", "AI 相关", "人工智能主题", "[]"),
        )

    localized = collection_store.list_tree(locale="zh-CN")

    assert localized[0]["name"] == "AI 相关"
    assert localized[0]["description"] == "人工智能主题"


@pytest.mark.asyncio
async def test_ai_uses_root_without_calling_provider_when_tree_is_empty(
    collection_store,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from src.core.collections import place_reviewed_article

    reviewed_path = tmp_path / "reviewed.md"
    reviewed_path.write_text("# Article\n", encoding="utf-8")

    async def unexpected_generate(*args, **kwargs):
        raise AssertionError("AI must not run without user-created collections")

    monkeypatch.setattr("src.integrations.ai_client.AIClient.generate_text", unexpected_generate)
    result = await place_reviewed_article("article", reviewed_path)

    assert result["collection_id"] is None
    assert result["confidence"] == 0


@pytest.mark.asyncio
async def test_ai_can_choose_any_existing_collection_depth(
    collection_store,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from src.core.collections import place_reviewed_article

    ai = collection_store.create_collection(name="AI")
    interviews = collection_store.create_collection(name="Interviews", parent_id=ai["id"])
    systems = collection_store.create_collection(name="System Design", parent_id=interviews["id"])
    reviewed_path = tmp_path / "reviewed.md"
    reviewed_path.write_text("# AI system design interview\n", encoding="utf-8")

    async def fake_generate(self, system_prompt: str, user_prompt: str):
        assert "Never create" in system_prompt
        assert "AI / Interviews / System Design" in user_prompt
        return SimpleNamespace(text=json.dumps({
            "collection_id": systems["id"],
            "confidence": 0.93,
            "reason": "The article is about AI system design interviews.",
        }))

    monkeypatch.setattr("src.integrations.ai_client.AIClient.generate_text", fake_generate)
    monkeypatch.setattr("src.integrations.ai_client.resolve_ai_settings", lambda config: SimpleNamespace())
    result = await place_reviewed_article("article", reviewed_path)

    assert result["collection_id"] == systems["id"]
    assert result["source"] == "ai"


@pytest.mark.asyncio
async def test_ai_unknown_or_low_confidence_choice_returns_to_root(
    collection_store,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from src.core.collections import place_reviewed_article

    ai = collection_store.create_collection(name="AI")
    reviewed_path = tmp_path / "reviewed.md"
    reviewed_path.write_text("# Unrelated article\n", encoding="utf-8")
    responses = iter([
        {"collection_id": "invented", "confidence": 0.95, "reason": "Invented"},
        {"collection_id": ai["id"], "confidence": 0.42, "reason": "Weak match"},
    ])

    async def fake_generate(self, system_prompt: str, user_prompt: str):
        return SimpleNamespace(text=json.dumps(next(responses)))

    monkeypatch.setattr("src.integrations.ai_client.AIClient.generate_text", fake_generate)
    monkeypatch.setattr("src.integrations.ai_client.resolve_ai_settings", lambda config: SimpleNamespace())
    unknown = await place_reviewed_article("article", reviewed_path)
    low_confidence = await place_reviewed_article("article", reviewed_path)

    assert unknown["collection_id"] is None
    assert "unknown collection" in unknown["reason"]
    assert low_confidence["collection_id"] is None
    assert low_confidence["confidence"] == pytest.approx(0.42)
