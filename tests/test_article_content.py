"""Tests for the article content database mirror and workspace recovery."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from src.core.config.config import clear_config_cache
from src.mcp.server import create_app

ARTICLE_ID = "wechat_mp_example_12345678"
RAW_MARKDOWN = "# Raw\n\nContext paragraph.\n"
REVIEWED_MARKDOWN = "# Reviewed\n\nContext paragraph.\n"
REFLECTION_MARKDOWN = "# Reflection\n\nWorth keeping.\n"
ANNOTATIONS_JSON = json.dumps({"version": 1, "annotations": []}, ensure_ascii=False)


@pytest.fixture
def content_store(monkeypatch, tmp_path: Path):
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
    from src.core.content import ArticleContentStore

    yield ArticleContentStore()
    clear_config_cache()


@pytest.fixture
def web_env(monkeypatch, tmp_path: Path):
    data_dir = tmp_path / ".noosphere"
    output_dir = data_dir / "articles"
    article_dir = output_dir / ARTICLE_ID
    article_dir.mkdir(parents=True)

    config_path = data_dir / "config.json"
    config_path.write_text(
        json.dumps({
            "output_dir": str(output_dir),
            "checkpoint": {"backend": "sqlite"},
        }),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "article_id": ARTICLE_ID,
        "article": {
            "platform": "wechat_mp",
            "platform_label": "WeChat",
            "url": "https://mp.weixin.qq.com/s/example",
            "title": "Example article",
            "author": "Lin",
            "published_at": "2026-07-01",
            "captured_at": "2026-07-20T08:00:00+00:00",
            "content_type": "article",
        },
        "paths": {"raw": "raw.md", "reviewed": "reviewed.md", "assets": "assets"},
        "assets": {"downloaded": [], "failed": {}},
    }
    (article_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (article_dir / "raw.md").write_text(RAW_MARKDOWN, encoding="utf-8")
    (article_dir / "reviewed.md").write_text(REVIEWED_MARKDOWN, encoding="utf-8")

    monkeypatch.setenv("NOOSPHERE_HOME", str(data_dir))
    monkeypatch.setenv("NOOSPHERE_CONFIG", str(config_path))
    clear_config_cache()
    yield output_dir, article_dir
    clear_config_cache()


def test_content_store_roundtrip(content_store) -> None:
    content_store.upsert_content(
        "article-1",
        title="Title",
        source_url="https://example.com/a",
        raw_markdown="# raw",
        reviewed_markdown="# reviewed",
    )
    row = content_store.get_content("article-1")
    assert row is not None
    assert row["title"] == "Title"
    assert row["source_url"] == "https://example.com/a"
    assert row["raw_markdown"] == "# raw"
    assert row["reviewed_markdown"] == "# reviewed"
    assert row["reflection_markdown"] == ""
    assert row["annotations_json"] == ""
    assert row["updated_at"]

    # Partial updates leave None fields untouched.
    content_store.upsert_content("article-1", reviewed_markdown="# reviewed v2")
    row = content_store.get_content("article-1")
    assert row["reviewed_markdown"] == "# reviewed v2"
    assert row["raw_markdown"] == "# raw"
    assert row["title"] == "Title"

    content_store.upsert_content("article-2", raw_markdown="# other")
    assert content_store.list_article_ids() == {"article-1", "article-2"}

    content_store.delete_content("article-1")
    assert content_store.get_content("article-1") is None
    assert content_store.list_article_ids() == {"article-2"}


def test_missing_article_directory_is_reconstructed_from_database(web_env) -> None:
    output_dir, article_dir = web_env
    with TestClient(create_app()) as client:
        from src.core.content import ArticleContentStore

        ArticleContentStore().upsert_content(
            ARTICLE_ID,
            title="Example article",
            source_url="https://mp.weixin.qq.com/s/example",
            raw_markdown=RAW_MARKDOWN,
            reviewed_markdown=REVIEWED_MARKDOWN,
            reflection_markdown=REFLECTION_MARKDOWN,
            annotations_json=ANNOTATIONS_JSON,
        )
        shutil.rmtree(article_dir)
        assert not article_dir.exists()

        response = client.get(f"/api/v1/articles/{ARTICLE_ID}")
        assert response.status_code == 200
        payload = response.json()
        assert payload["rawMarkdown"] == RAW_MARKDOWN
        assert payload["reviewedMarkdown"] == REVIEWED_MARKDOWN
        # Title display prefers the Markdown heading, per _article_summary.
        assert payload["title"] == "Reviewed"

        assert article_dir.is_dir()
        assert (article_dir / "raw.md").read_text(encoding="utf-8") == RAW_MARKDOWN
        assert (article_dir / "reviewed.md").read_text(encoding="utf-8") == REVIEWED_MARKDOWN
        assert (article_dir / "reflection.md").read_text(encoding="utf-8") == REFLECTION_MARKDOWN
        assert (article_dir / "annotations.json").read_text(encoding="utf-8") == ANNOTATIONS_JSON
        manifest = json.loads((article_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["article_id"] == ARTICLE_ID
        assert manifest["article"]["title"] == "Example article"
        assert manifest["article"]["url"] == "https://mp.weixin.qq.com/s/example"
        assert output_dir == article_dir.parent


def test_startup_recovery_rebuilds_missing_workspaces(web_env) -> None:
    _, article_dir = web_env
    from src.core.content import ArticleContentStore

    ArticleContentStore().upsert_content(
        ARTICLE_ID,
        title="Example article",
        source_url="https://mp.weixin.qq.com/s/example",
        raw_markdown=RAW_MARKDOWN,
        reviewed_markdown=REVIEWED_MARKDOWN,
    )
    shutil.rmtree(article_dir)

    with TestClient(create_app()):
        assert article_dir.is_dir()
        assert (article_dir / "reviewed.md").read_text(encoding="utf-8") == REVIEWED_MARKDOWN


def test_trashed_article_is_not_resurrected_by_startup_recovery(web_env) -> None:
    output_dir, article_dir = web_env
    with TestClient(create_app()) as client:
        from src.core.content import ArticleContentStore, recover_missing_article_workspaces

        store = ArticleContentStore()
        store.upsert_content(
            ARTICLE_ID,
            title="Example article",
            raw_markdown=RAW_MARKDOWN,
            reviewed_markdown=REVIEWED_MARKDOWN,
        )

        # Soft-delete moves the workspace out of the output directory.
        trash_response = client.delete(f"/api/v1/articles/{ARTICLE_ID}")
        assert trash_response.status_code == 200
        assert not article_dir.exists()

        # Startup recovery must not resurrect trashed articles from the mirror.
        assert recover_missing_article_workspaces(output_dir) == 0
        assert not article_dir.exists()

        # Direct reconstruction is skipped as well while the trash record exists.
        from src.core.content import reconstruct_article_workspace

        assert reconstruct_article_workspace(ARTICLE_ID, output_dir) is None
        assert not article_dir.exists()


def test_unknown_article_still_404(web_env) -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/articles/wechat_mp_missing_00000000")
        assert response.status_code == 404


def test_permanent_delete_removes_content_row(web_env) -> None:
    _, article_dir = web_env
    assert article_dir.is_dir()
    with TestClient(create_app()) as client:
        from src.core.content import ArticleContentStore

        store = ArticleContentStore()
        store.upsert_content(ARTICLE_ID, raw_markdown=RAW_MARKDOWN)

        trash_response = client.delete(f"/api/v1/articles/{ARTICLE_ID}")
        assert trash_response.status_code == 200
        assert store.get_content(ARTICLE_ID) is not None

        delete_response = client.delete(f"/api/v1/trash/articles/{ARTICLE_ID}")
        assert delete_response.status_code == 200
        assert store.get_content(ARTICLE_ID) is None
        assert ARTICLE_ID not in store.list_article_ids()
