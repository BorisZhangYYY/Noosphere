"""Tests for the empty, user-owned taxonomy foundation."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.config.config import clear_config_cache


@pytest.fixture
def catalog_store(monkeypatch, tmp_path: Path):
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
    from src.core.catalog import CatalogStore

    yield CatalogStore()
    clear_config_cache()


def test_new_workspace_starts_without_product_categories(catalog_store) -> None:
    assert catalog_store.list_tree("zh-CN") == []
    assert catalog_store.list_tree("en-US") == []


def test_user_created_categories_survive_repeated_reads(catalog_store) -> None:
    assignment = catalog_store.assign(
        "existing-article",
        tag_name="Software Engineering",
        tag_description="Engineering practices for building software.",
        subtag_name="AI-Assisted Development",
        subtag_description="Using AI in software delivery workflows.",
        tag_localizations={
            "en-US": {"name": "Software Engineering", "description": "Engineering practices for building software."},
            "zh-CN": {"name": "软件工程", "description": "构建软件的工程实践。"},
        },
        subtag_localizations={
            "en-US": {"name": "AI-Assisted Development", "description": "Using AI in software delivery workflows."},
            "zh-CN": {"name": "AI 辅助开发", "description": "在软件交付中使用 AI。"},
        },
    )

    first = catalog_store.list_tree("zh-CN")
    second = catalog_store.list_tree("zh-CN")

    assert second == first
    assert len(first) == 1
    assert first[0]["id"] == assignment["tag_id"]
    assert first[0]["name"] == "软件工程"
    assert first[0]["children"][0]["id"] == assignment["subtag_id"]
    assert first[0]["children"][0]["name"] == "AI 辅助开发"
    assert all(not item["id"].startswith("builtin-") for item in first)


def test_category_management_enforces_two_levels_and_retirement(catalog_store) -> None:
    root = catalog_store.create_category(
        name="Software Engineering",
        description="Building maintainable software systems.",
    )
    child = catalog_store.create_category(
        name="AI-Assisted Development",
        description="AI-supported delivery workflows.",
        parent_id=root["id"],
    )

    with pytest.raises(ValueError, match="two levels"):
        catalog_store.create_category(name="Too deep", parent_id=child["id"])
    with pytest.raises(ValueError, match="already exists"):
        catalog_store.create_category(name="software engineering")

    updated = catalog_store.update_category(
        root["id"],
        name="软件工程",
        description="构建可维护的软件系统。",
        locale="zh-CN",
    )
    assert updated["name"] == "软件工程"
    assignment = catalog_store.assign_existing(
        "article",
        tag_id=root["id"],
        subtag_id=child["id"],
    )
    assert assignment["subtag_id"] == child["id"]
    retired = catalog_store.update_category(root["id"], retired=True)
    assert retired["retired"] is True
    assert catalog_store.list_tree() == []
    assert catalog_store.get_assignment("article") is None
    assert catalog_store.get_search_terms("article") == []
    with pytest.raises(ValueError, match="retired"):
        catalog_store.assign_existing("article", tag_id=root["id"], subtag_id=child["id"])

    restored = catalog_store.update_category(root["id"], retired=False)
    assert restored["retired"] is False
    restored_assignment = catalog_store.get_assignment("article")
    assert restored_assignment is not None
    assert restored_assignment["tag_id"] == root["id"]
    assert restored_assignment["subtag_id"] == child["id"]


@pytest.mark.asyncio
async def test_auto_classification_skips_ai_when_taxonomy_is_empty(
    catalog_store,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from src.core.catalog import classify_reviewed_article

    reviewed_path = tmp_path / "reviewed.md"
    reviewed_path.write_text("# Article\n", encoding="utf-8")

    async def unexpected_generate(*args, **kwargs):
        raise AssertionError("AI must not run without user-configured categories")

    monkeypatch.setattr("src.integrations.ai_client.AIClient.generate_text", unexpected_generate)
    result = await classify_reviewed_article("article", reviewed_path)

    assert result["classified"] is False
    assert result["confidence"] == 0
    assert catalog_store.get_assignment("article") is None


@pytest.mark.asyncio
async def test_auto_classification_only_assigns_existing_category_ids(
    catalog_store,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from src.core.catalog import classify_reviewed_article

    root = catalog_store.create_category(name="Software Engineering", description="Software delivery.")
    child = catalog_store.create_category(
        name="AI-Assisted Development",
        description="AI tools used in software delivery.",
        parent_id=root["id"],
    )
    reviewed_path = tmp_path / "reviewed.md"
    reviewed_path.write_text("# Coding agents\n\nAI-assisted engineering practices.", encoding="utf-8")

    async def fake_generate(self, system_prompt: str, user_prompt: str):
        assert "Never create" in system_prompt
        assert root["id"] in user_prompt
        return SimpleNamespace(text=json.dumps({
            "tag_id": root["id"],
            "subtag_id": child["id"],
            "confidence": 0.91,
            "reason": "The article covers AI-supported delivery.",
        }))

    monkeypatch.setattr("src.integrations.ai_client.AIClient.generate_text", fake_generate)
    monkeypatch.setattr("src.integrations.ai_client.resolve_ai_settings", lambda config: SimpleNamespace())
    result = await classify_reviewed_article("article", reviewed_path)

    assert result["classified"] is True
    assert result["tag_id"] == root["id"]
    assert result["subtag_id"] == child["id"]
    assert result["confidence"] == pytest.approx(0.91)
    assert result["source"] == "ai"
    assert len(catalog_store.list_tree()) == 1


@pytest.mark.asyncio
async def test_auto_classification_rejects_unknown_or_low_confidence_results(
    catalog_store,
    monkeypatch,
    tmp_path: Path,
) -> None:
    from src.core.catalog import classify_reviewed_article

    root = catalog_store.create_category(name="Software Engineering")
    catalog_store.assign_existing("article", tag_id=root["id"])
    reviewed_path = tmp_path / "reviewed.md"
    reviewed_path.write_text("# Unrelated article\n", encoding="utf-8")
    responses = iter([
        {"tag_id": "invented-category", "subtag_id": None, "confidence": 0.95, "reason": "Invented"},
        {"tag_id": root["id"], "subtag_id": None, "confidence": 0.42, "reason": "Weak match"},
    ])

    async def fake_generate(self, system_prompt: str, user_prompt: str):
        return SimpleNamespace(text=json.dumps(next(responses)))

    monkeypatch.setattr("src.integrations.ai_client.AIClient.generate_text", fake_generate)
    monkeypatch.setattr("src.integrations.ai_client.resolve_ai_settings", lambda config: SimpleNamespace())
    unknown = await classify_reviewed_article("article", reviewed_path)
    low_confidence = await classify_reviewed_article("article", reviewed_path)

    assert unknown["classified"] is False
    assert "unknown category" in unknown["reason"]
    assert low_confidence["classified"] is False
    assert low_confidence["confidence"] == pytest.approx(0.42)
    assert catalog_store.get_assignment("article") is None
    assert [item["name"] for item in catalog_store.list_tree()] == ["Software Engineering"]
