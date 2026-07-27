"""Boundary validation tests for the MCP service."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.mcp.server import (
    classify_article,
    get_job,
    list_articles,
    list_taxonomy,
    list_review_perspectives,
    _validate_article_id,
    _validate_upload_target,
    review_article,
    run_pipeline,
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
async def test_classify_article_prefers_canonical_ids(monkeypatch) -> None:
    received: dict[str, object] = {}

    def fake_classify(article_id: str, **kwargs):
        received.update(article_id=article_id, **kwargs)
        return {"tag_id": kwargs["tag_id"], "subtag_id": kwargs["subtag_id"]}

    monkeypatch.setattr("src.application.service.classify_article", fake_classify)

    result = await classify_article("article", tag_id="tag-1", subtag_id="subtag-1", locale="zh-CN")

    assert result["classification"] == {"tag_id": "tag-1", "subtag_id": "subtag-1"}
    assert received["tag_id"] == "tag-1"
    assert received["subtag_id"] == "subtag-1"
    assert received["locale"] == "zh-CN"


@pytest.mark.asyncio
async def test_list_taxonomy_includes_processing_profile(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.application.service.get_processing_profile",
        lambda **kwargs: {"id": "developer", "locale": kwargs["locale"]},
    )
    monkeypatch.setattr(
        "src.application.service.list_taxonomy",
        lambda **kwargs: [{"id": "category-1", "locale": kwargs["locale"]}],
    )

    result = await list_taxonomy("zh-CN")

    assert result["profile"] == {"id": "developer", "locale": "zh-CN"}
    assert result["tags"] == [{"id": "category-1", "locale": "zh-CN"}]


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
