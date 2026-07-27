"""Tests for the empty, user-owned taxonomy foundation."""
from __future__ import annotations

import json
from pathlib import Path

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
    retired = catalog_store.update_category(root["id"], retired=True)
    assert retired["retired"] is True
    assert catalog_store.list_tree() == []
    with pytest.raises(ValueError, match="retired"):
        catalog_store.assign_existing("article", tag_id=root["id"], subtag_id=child["id"])

    restored = catalog_store.update_category(root["id"], retired=False)
    assert restored["retired"] is False
    assignment = catalog_store.assign_existing(
        "article",
        tag_id=root["id"],
        subtag_id=child["id"],
    )
    assert assignment["tag_id"] == root["id"]
    assert assignment["subtag_id"] == child["id"]
