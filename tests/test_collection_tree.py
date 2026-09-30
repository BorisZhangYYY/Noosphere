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


@pytest.mark.asyncio
async def test_suggest_collection_description_includes_tree_context(
    collection_store,
    monkeypatch,
) -> None:
    from src.core.collections import suggest_collection_description

    parent = collection_store.create_collection(name="AI 相关")
    collection_store.create_collection(name="AI 测评", description="模型与产品的能力评测", parent_id=parent["id"])

    async def fake_generate(self, system_prompt: str, user_prompt: str):
        assert "Collection description request" in user_prompt
        assert "AI 相关" in user_prompt
        assert "AI 测评" in user_prompt
        assert '"task": "create"' in user_prompt
        return SimpleNamespace(
            text=json.dumps({
                "description": "AI 工具的落地实践与使用指南。",
                "reasoning": "The name signals tooling practice.",
            }),
            model="test-model",
            provider="test",
        )

    monkeypatch.setattr("src.integrations.ai_client.AIClient.generate_text", fake_generate)
    monkeypatch.setattr("src.integrations.ai_client.resolve_ai_settings", lambda config: SimpleNamespace())
    result = await suggest_collection_description("AI 工具", parent_id=parent["id"], hint="聚焦实操")

    assert result["description"] == "AI 工具的落地实践与使用指南。"
    assert result["reasoning"]
    assert result["model"] == "test-model"


@pytest.mark.asyncio
async def test_suggest_collection_description_at_root_has_empty_context(
    collection_store,
    monkeypatch,
) -> None:
    from src.core.collections import suggest_collection_description

    async def fake_generate(self, system_prompt: str, user_prompt: str):
        assert '"parent_path": []' in user_prompt
        assert '"sibling_collections": []' in user_prompt
        return SimpleNamespace(
            text=json.dumps({"description": "游戏相关文章。", "reasoning": "Root gaming bucket."}),
            model="test-model",
            provider="test",
        )

    monkeypatch.setattr("src.integrations.ai_client.AIClient.generate_text", fake_generate)
    monkeypatch.setattr("src.integrations.ai_client.resolve_ai_settings", lambda config: SimpleNamespace())
    result = await suggest_collection_description("游戏相关")

    assert result["description"] == "游戏相关文章。"


@pytest.mark.asyncio
async def test_suggest_collection_description_uses_root_siblings_but_excludes_itself(
    collection_store,
    monkeypatch,
) -> None:
    from src.core.collections import suggest_collection_description

    existing = collection_store.create_collection(name="AI 相关", description="AI 新闻与实践")
    target = collection_store.create_collection(name="游戏相关")

    async def fake_generate(self, system_prompt: str, user_prompt: str):
        request = json.loads(user_prompt.split("Collection description request:\n", 1)[1])
        assert request["parent_path"] == []
        assert request["sibling_collections"] == [
            {"name": existing["name"], "description": existing["description"]}
        ]
        return SimpleNamespace(
            text=json.dumps({"description": "游戏相关文章。", "reasoning": "Distinct root topic."}),
            model="test-model",
            provider="test",
        )

    monkeypatch.setattr("src.integrations.ai_client.AIClient.generate_text", fake_generate)
    monkeypatch.setattr("src.integrations.ai_client.resolve_ai_settings", lambda config: SimpleNamespace())
    await suggest_collection_description(target["name"], exclude_collection_id=target["id"])


def test_description_locale_requires_selection_and_updates_only_selected_language(collection_store) -> None:
    collection = collection_store.create_collection(name="AI", description="English base")
    collection_store.update_collection(collection["id"], name="人工智能", description="中文原文", locale="zh-CN")

    with pytest.raises(ValueError, match="choose locale"):
        collection_store.resolve_description_locale(collection["id"])

    selected = collection_store.resolve_description_locale(collection["id"], "zh-CN")
    assert selected == "zh-CN"
    collection_store.update_collection(collection["id"], description="中文润色", locale=selected)
    assert collection_store.get_collection(collection["id"], locale="zh-CN")["description"] == "中文润色"
    assert collection_store.get_collection(collection["id"])["description"] == "English base"
    assert collection_store.resolve_description_locale(collection["id"], "base") is None


@pytest.mark.asyncio
async def test_mcp_and_cli_apply_description_to_selected_locale(
    collection_store,
    monkeypatch,
    capsys,
) -> None:
    from src.cli import _main_async, parse_args
    from src.mcp.server import polish_collection_description as mcp_polish_description

    collection = collection_store.create_collection(name="AI", description="English base")
    collection_store.update_collection(collection["id"], name="人工智能", description="中文原文", locale="zh-CN")

    async def fake_generate(self, system_prompt: str, user_prompt: str):
        request = json.loads(user_prompt.split("Collection description request:\n", 1)[1])
        source = request["existing_description"]
        return SimpleNamespace(
            text=json.dumps({"description": f"{source} improved", "reasoning": "Clearer wording."}),
            model="test-model",
            provider="test",
        )

    monkeypatch.setattr("src.integrations.ai_client.AIClient.generate_text", fake_generate)
    monkeypatch.setattr("src.integrations.ai_client.resolve_ai_settings", lambda config: SimpleNamespace())

    with pytest.raises(ValueError, match="choose locale"):
        await mcp_polish_description(collection["id"], apply=True)

    mcp_result = await mcp_polish_description(collection["id"], locale="zh-CN", apply=True)
    assert mcp_result["locale"] == "zh-CN"
    assert collection_store.get_collection(collection["id"], locale="zh-CN")["description"] == "中文原文 improved"
    assert collection_store.get_collection(collection["id"])["description"] == "English base"

    exit_code = await _main_async(parse_args([
        "collections", "describe", collection["id"], "--locale", "base", "--apply", "--json",
    ]))
    cli_result = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert cli_result["locale"] == "base"
    assert collection_store.get_collection(collection["id"])["description"] == "English base improved"
    assert collection_store.get_collection(collection["id"], locale="zh-CN")["description"] == "中文原文 improved"


@pytest.mark.asyncio
async def test_suggest_collection_description_rejects_unknown_parent(
    collection_store,
    monkeypatch,
) -> None:
    from src.core.collections import suggest_collection_description

    async def unexpected_generate(*args, **kwargs):
        raise AssertionError("AI must not run for an unknown parent")

    monkeypatch.setattr("src.integrations.ai_client.AIClient.generate_text", unexpected_generate)
    with pytest.raises(ValueError, match="Collection not found"):
        await suggest_collection_description("孤儿分类", parent_id="missing-id")


@pytest.mark.asyncio
async def test_polish_collection_description_keeps_intent(
    collection_store,
    monkeypatch,
) -> None:
    from src.core.collections import polish_collection_description

    async def fake_generate(self, system_prompt: str, user_prompt: str):
        assert '"task": "polish"' in user_prompt
        assert "现有描述" in user_prompt
        return SimpleNamespace(
            text=json.dumps({"description": "更清晰的描述。", "reasoning": "Kept the intent."}),
            model="test-model",
            provider="test",
        )

    monkeypatch.setattr("src.integrations.ai_client.AIClient.generate_text", fake_generate)
    monkeypatch.setattr("src.integrations.ai_client.resolve_ai_settings", lambda config: SimpleNamespace())
    result = await polish_collection_description("AI 工具", "现有描述")

    assert result["description"] == "更清晰的描述。"


@pytest.mark.asyncio
async def test_polish_collection_description_requires_existing_text(
    collection_store,
    monkeypatch,
) -> None:
    from src.core.collections import polish_collection_description

    async def unexpected_generate(*args, **kwargs):
        raise AssertionError("AI must not run without an existing description")

    monkeypatch.setattr("src.integrations.ai_client.AIClient.generate_text", unexpected_generate)
    with pytest.raises(ValueError, match="required to polish"):
        await polish_collection_description("AI 工具", "   ")
