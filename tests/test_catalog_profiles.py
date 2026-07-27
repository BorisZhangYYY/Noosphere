"""Tests for Noosphere-owned article-organization profiles."""
from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
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

    yield CatalogStore(), runtime_home
    clear_config_cache()


def test_developer_profile_seeds_localized_starter_taxonomy(catalog_store) -> None:
    store, _ = catalog_store

    profile = store.get_processing_profile("zh-CN")
    tree = store.list_tree("zh-CN")
    roots = {item["id"]: item for item in tree}

    assert profile["id"] == "developer"
    assert profile["version"] == 1
    assert profile["builtin"] is True
    assert profile["editable"] is False
    assert profile["name"] == "开发者"
    assert profile["inboxCategoryId"] == "builtin-developer-inbox"
    assert set(roots) == {
        "builtin-developer-ai-software",
        "builtin-developer-games",
        "builtin-developer-tools-productivity",
        "builtin-developer-inbox",
    }
    assert roots["builtin-developer-ai-software"]["name"] == "AI 与软件"
    assert {
        child["id"]
        for child in roots["builtin-developer-ai-software"]["children"]
    } == {
        "builtin-developer-agent-coding",
        "builtin-developer-applied-ai",
        "builtin-developer-models-industry",
        "builtin-developer-software-engineering",
        "builtin-developer-career-growth",
    }
    assert "zhujilu" not in json.dumps({"profile": profile, "tree": tree}).casefold()


def test_profile_application_is_idempotent(catalog_store) -> None:
    store, runtime_home = catalog_store

    first = store.get_processing_profile()
    first_tree = store.list_tree()
    second = store.get_processing_profile()
    second_tree = store.list_tree()

    assert second["appliedAt"] == first["appliedAt"]
    assert second_tree == first_tree
    with sqlite3.connect(runtime_home / "catalog.sqlite3") as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM noosphere_catalog_profile"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM noosphere_tags WHERE id LIKE 'builtin-developer-%'"
        ).fetchone()[0] == 14


def test_profile_application_is_safe_for_concurrent_first_reads(catalog_store) -> None:
    store, runtime_home = catalog_store

    with ThreadPoolExecutor(max_workers=4) as executor:
        profiles = list(executor.map(
            lambda _: store.get_processing_profile(),
            range(4),
        ))

    assert len({profile["appliedAt"] for profile in profiles}) == 1
    with sqlite3.connect(runtime_home / "catalog.sqlite3") as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM noosphere_catalog_profile"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM noosphere_tags WHERE id LIKE 'builtin-developer-%'"
        ).fetchone()[0] == 14


def test_starter_taxonomy_preserves_existing_categories(catalog_store) -> None:
    store, _ = catalog_store
    custom = store.assign(
        "existing-article",
        tag_name="Security",
        tag_description="Application and infrastructure security.",
    )

    tree = store.list_tree()

    assert any(item["id"] == custom["tag_id"] for item in tree)
    assert any(item["id"] == "builtin-developer-ai-software" for item in tree)
