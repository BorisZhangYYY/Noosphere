"""Boundary validation tests for the MCP service."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.mcp.server import (
    create_collection,
    delete_collection,
    get_article_reflection,
    get_job,
    list_articles,
    list_collections,
    list_review_perspectives,
    place_article,
    polish_article_reflection,
    _validate_article_id,
    _validate_upload_target,
    review_article,
    restore_collection,
    run_pipeline,
    save_article_reflection,
    update_collection,
)


@pytest.mark.parametrize("article_id", ["", " ", ".", "..", "../outside", "nested/article", r"nested\\article"])
def test_article_id_rejects_paths(article_id: str) -> None:
    with pytest.raises(ValueError):
        _validate_article_id(article_id)


def test_article_id_accepts_workspace_name() -> None:
    assert _validate_article_id("wechat_mp_article_12345678") == "wechat_mp_article_12345678"


@pytest.mark.parametrize("target, expected", [("auto", None), ("local", "local"), ("siyuan", "siyuan")])
def test_upload_target_accepts_supported_values(target: str, expected: str | None) -> None:
    assert _validate_upload_target(target) == expected


@pytest.mark.parametrize("target", ["", "filesystem", "AUTO"])
def test_upload_target_rejects_unknown_values(target: str) -> None:
    with pytest.raises(ValueError):
        _validate_upload_target(target)


@pytest.mark.asyncio
async def test_review_article_passes_perspective_to_graph(monkeypatch, tmp_path: Path) -> None:
    article_dir = tmp_path / "article"
    article_dir.mkdir()
    (article_dir / "reviewed.md").write_text("# Article\n", encoding="utf-8")
    received: dict[str, object] = {}

    async def fake_review(path: Path, *, perspective: str | None = None, output_language: str | None = None):
        received.update(path=path, perspective=perspective, output_language=output_language)
        return SimpleNamespace(ok=True, issues=[])

    monkeypatch.setattr("src.mcp.server._resolve_article_dir", lambda article_id: article_dir)
    monkeypatch.setattr("src.graph.graph.run_ai_review_graph", fake_review)

    result = await review_article("article", perspective="novice", language="en-US")

    assert result["ok"] is True
    assert result["status"] == "reviewed"
    assert result["article_id"] == "article"
    assert received == {"path": article_dir / "reviewed.md", "perspective": "novice", "output_language": "en-US"}


@pytest.mark.asyncio
async def test_run_pipeline_passes_perspective_to_graph(monkeypatch) -> None:
    received: dict[str, object] = {}

    async def fake_pipeline(url: str, *, auto_confirm: bool, perspective: str | None = None, output_language: str | None = None):
        received.update(url=url, auto_confirm=auto_confirm, perspective=perspective, output_language=output_language)
        return SimpleNamespace(hpath="/Noosphere/Article", created=True)

    monkeypatch.setattr("src.graph.graph.run_pipeline_graph", fake_pipeline)

    result = await run_pipeline(
        "https://example.com/article",
        auto_confirm=False,
        perspective="novice",
        language="zh-CN",
    )

    assert result["ok"] is True
    assert result["status"] == "uploaded"
    assert result["hpath"] == "/Noosphere/Article"
    assert received == {
        "url": "https://example.com/article",
        "auto_confirm": False,
        "perspective": "novice",
        "output_language": "zh-CN",
    }


@pytest.mark.asyncio
async def test_list_articles_returns_structured_pagination(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.application.service.list_articles",
        lambda **kwargs: [{"id": "a"}, {"id": "b"}, {"id": "c"}],
    )

    result = await list_articles(limit=1, offset=1)

    assert result == {
        "ok": True,
        "total": 3,
        "offset": 1,
        "limit": 1,
        "articles": [{"id": "b"}],
    }


@pytest.mark.asyncio
async def test_place_article_uses_existing_collection_id(monkeypatch) -> None:
    received: dict[str, object] = {}

    def fake_place(article_id: str, **kwargs):
        received.update(article_id=article_id, **kwargs)
        return {"collection_id": kwargs["collection_id"]}

    monkeypatch.setattr("src.application.service.place_article", fake_place)

    result = await place_article("article", collection_id="collection-1")

    assert result["collection"] == {"collection_id": "collection-1"}
    assert received["collection_id"] == "collection-1"


@pytest.mark.asyncio
async def test_place_article_forwards_explicit_leaf_creation_authority(monkeypatch) -> None:
    received: dict[str, object] = {}

    def fake_place(article_id: str, **kwargs):
        received.update(article_id=article_id, **kwargs)
        return {"collection_id": "evaluation", "created_collections": [{"id": "evaluation"}]}

    monkeypatch.setattr("src.application.service.place_article", fake_place)

    result = await place_article(
        "article",
        collection_path=["AI 相关", "AI 测评"],
        create_missing=True,
        collection_description="以正文中的模型能力与实测结果为主。",
    )

    assert result["collection"]["collection_id"] == "evaluation"
    assert received["collection_path"] == ["AI 相关", "AI 测评"]
    assert received["create_missing"] is True
    assert received["collection_description"] == "以正文中的模型能力与实测结果为主。"


@pytest.mark.asyncio
async def test_list_collections_returns_user_owned_tree(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.application.service.list_collections",
        lambda **kwargs: [{"id": "collection-1", "deleted": kwargs["include_deleted"]}],
    )

    result = await list_collections()

    assert "profile" not in result
    assert result["collections"] == [{"id": "collection-1", "deleted": False}]


@pytest.mark.asyncio
async def test_collection_management_tools_delegate_to_application(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.application.service.create_collection",
        lambda **kwargs: {"id": "new", **kwargs},
    )
    monkeypatch.setattr(
        "src.application.service.update_collection",
        lambda collection_id, **kwargs: {"id": collection_id, **kwargs},
    )

    created = await create_collection(
        "Engineering",
        "Software practices",
    )
    updated = await update_collection(
        "new",
        name="软件工程",
        retired=True,
    )

    assert created["collection"]["id"] == "new"
    assert created["collection"]["name"] == "Engineering"
    assert updated["collection"]["id"] == "new"
    assert updated["collection"]["name"] == "软件工程"
    assert updated["collection"]["retired"] is True


@pytest.mark.asyncio
async def test_collection_delete_and_restore_tools_are_recoverable(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []

    def fake_update(collection_id: str, *, retired: bool):
        calls.append((collection_id, retired))
        return {"id": collection_id, "retired": retired}

    monkeypatch.setattr("src.application.service.update_collection", fake_update)

    deleted = await delete_collection("collection-1")
    restored = await restore_collection("collection-1")

    assert deleted["deleted"] is True
    assert deleted["recoverable"] is True
    assert restored["deleted"] is False
    assert restored["recoverable"] is True
    assert calls == [
        ("collection-1", True),
        ("collection-1", False),
    ]


@pytest.mark.asyncio
async def test_list_review_perspectives_returns_contract(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.application.service.get_pipeline_settings",
        lambda **kwargs: {
            "activePerspective": "original",
            "reviewMode": "ai_then_manual",
            "outputLanguage": "source",
            "perspectives": [{"id": "original", "outputSections": {"body": "Article"}}],
        },
    )

    result = await list_review_perspectives("en-US")

    assert result["active_perspective"] == "original"
    assert result["perspectives"][0]["outputSections"] == {"body": "Article"}


@pytest.mark.asyncio
async def test_get_job_returns_background_job(monkeypatch) -> None:
    monkeypatch.setattr("src.api.web.get_background_job", lambda job_id: {"id": job_id, "status": "running"})

    result = await get_job("job-1")

    assert result == {"id": "job-1", "status": "running"}


@pytest.mark.asyncio
async def test_reflection_tools_delegate_to_shared_service(monkeypatch, tmp_path: Path) -> None:
    article_dir = tmp_path / "article"
    article_dir.mkdir()
    monkeypatch.setattr("src.mcp.server._resolve_article_dir", lambda article_id: article_dir)
    saved: dict[str, object] = {}

    def fake_save(article_id: str, markdown=None, *, upload_enabled=None):
        saved.update(article_id=article_id, markdown=markdown, upload_enabled=upload_enabled)
        return {"articleId": article_id, "markdown": markdown or "", "uploadEnabled": bool(upload_enabled), "exists": bool(markdown)}

    monkeypatch.setattr("src.application.service.save_reflection", fake_save)
    monkeypatch.setattr(
        "src.application.service.get_reflection",
        lambda article_id: {"articleId": article_id, "markdown": "Saved", "uploadEnabled": True, "exists": True},
    )
    result = await save_article_reflection("article", "Draft", upload_enabled=True)
    shown = await get_article_reflection("article")
    assert result["markdown"] == "Draft"
    assert saved == {"article_id": "article", "markdown": "Draft", "upload_enabled": True}
    assert shown["markdown"] == "Saved"


@pytest.mark.asyncio
async def test_polish_tool_applies_only_when_requested(monkeypatch, tmp_path: Path) -> None:
    article_dir = tmp_path / "article"
    article_dir.mkdir()
    (article_dir / "reviewed.md").write_text("# Article\n", encoding="utf-8")
    monkeypatch.setattr("src.mcp.server._resolve_article_dir", lambda article_id: article_dir)

    async def fake_polish(reviewed_path, *, reflection=None):
        return {"markdown": "Polished", "model": "m", "provider": "p"}

    applied: list[str] = []
    monkeypatch.setattr("src.graph.graph.run_reflection_graph", fake_polish)
    monkeypatch.setattr(
        "src.application.service.save_reflection",
        lambda article_id, markdown: applied.append(markdown),
    )
    preview = await polish_article_reflection("article")
    assert preview["status"] == "polished"
    assert applied == []
    applied_result = await polish_article_reflection("article", apply=True)
    assert applied_result["status"] == "applied"
    assert applied == ["Polished"]
