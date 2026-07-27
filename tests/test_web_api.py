"""Tests for the HTTP API consumed by the web frontend."""
from __future__ import annotations

import asyncio
import json
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from src.core.config.config import clear_config_cache, load_config
from src.mcp.server import create_app
from src.api.web import _capture_jobs, _review_jobs, _upload_jobs


@pytest.fixture
def web_client(monkeypatch, tmp_path: Path):
    data_dir = tmp_path / ".noosphere"
    output_dir = data_dir / "articles"
    article_dir = output_dir / "wechat_mp_example_12345678"
    assets_dir = article_dir / "assets"
    assets_dir.mkdir(parents=True)

    config_path = data_dir / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "ai": {"provider": "openai"},
                "ai_providers": {
                    "openai": {
                        "api_format": "openai_chat",
                        "model": "test-model",
                        "api_base": "https://api.example.test/v1",
                        "api_key": "existing-secret",
                    },
                    "Kimi Backup": {
                        "api_format": "openai_chat",
                        "model": "kimi-model",
                        "api_base": "https://models.example.test/v1",
                        "api_key": "kimi-secret",
                    },
                    "MiniMax Backup": {
                        "api_format": "anthropic",
                        "model": "minimax-model",
                        "api_base": "https://models.example.test/anthropic",
                        "api_key": "minimax-secret",
                    },
                    "GLM Backup": {
                        "api_format": "openai_chat",
                        "model": "glm-model",
                        "api_base": "https://open.bigmodel.cn/api/paas/v4",
                        "api_key": "zhipu-secret",
                    },
                    "Doubao Work": {
                        "api_format": "openai_chat",
                        "model": "doubao-model",
                        "api_base": "https://models.example.test/v1",
                        "api_key": "volcengine-secret",
                    },
                },
                "crawler": {
                    "primary": "crawl4ai",
                    "fallback": "firecrawl",
                    "firecrawl": {"api_key": "firecrawl-secret"},
                },
                "siyuan": {
                    "api_base": "http://127.0.0.1:6806",
                    "token": "siyuan-secret",
                },
            }
        ),
        encoding="utf-8",
    )
    manifest = {
        "article_id": article_dir.name,
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
        "assets": {"downloaded": [{"local_path": "assets/image.png"}], "failed": {}},
    }
    (article_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (article_dir / "raw.md").write_text("# Raw\n\nContext paragraph.\n\n![diagram](assets/image.png)\n", encoding="utf-8")
    (article_dir / "reviewed.md").write_text("# Reviewed\n\nContext paragraph.\n\n![diagram](assets/image.png)\n", encoding="utf-8")
    (assets_dir / "image.png").write_bytes(b"not-a-real-png")

    monkeypatch.setenv("NOOSPHERE_HOME", str(data_dir))
    monkeypatch.setenv("NOOSPHERE_CONFIG", str(config_path))
    monkeypatch.setenv("NOOSPHERE_OUTPUT_DIR", str(output_dir))
    clear_config_cache()
    _capture_jobs.clear()
    _review_jobs.clear()
    _upload_jobs.clear()
    with TestClient(create_app()) as client:
        yield client, config_path, article_dir.name
    _capture_jobs.clear()
    _review_jobs.clear()
    _upload_jobs.clear()
    clear_config_cache()


def test_list_and_read_article(web_client) -> None:
    client, _, article_id = web_client
    listing = client.get("/api/v1/articles")
    assert listing.status_code == 200
    assert listing.json()["articles"][0]["id"] == article_id

    detail = client.get(f"/api/v1/articles/{article_id}")
    assert detail.status_code == 200
    assert detail.json()["reviewedMarkdown"].startswith("# Reviewed\n")
    assert "assets/image.png" in detail.json()["displayMarkdown"]
    assert detail.json()["assets"][0]["name"] == "image.png"


def test_article_listing_degrades_when_database_metadata_is_unavailable(web_client, monkeypatch) -> None:
    client, _, article_id = web_client

    def unavailable(*args, **kwargs):
        del args, kwargs
        raise ConnectionError("database offline")

    monkeypatch.setattr("src.core.catalog.CatalogStore.get_assignment", unavailable)
    monkeypatch.setattr("src.core.activity.ArticleActivityStore.backfill_workspace", unavailable)

    response = client.get("/api/v1/articles")

    assert response.status_code == 200
    article = response.json()["articles"][0]
    assert article["id"] == article_id
    assert article["classification"] is None
    assert article["operationSummary"]["captureCount"] == 0


def test_articles_support_batch_trash_restore_and_permanent_delete(web_client) -> None:
    client, config_path, article_id = web_client
    output_dir = config_path.parent / "articles"
    second_id = "wechat_mp_second_87654321"
    second_dir = output_dir / second_id
    shutil.copytree(output_dir / article_id, second_dir)
    second_manifest_path = second_dir / "manifest.json"
    second_manifest = json.loads(second_manifest_path.read_text(encoding="utf-8"))
    second_manifest["article_id"] = second_id
    second_manifest["article"]["title"] = "Second article"
    second_manifest_path.write_text(json.dumps(second_manifest), encoding="utf-8")
    assert client.patch(
        f"/api/v1/articles/{article_id}/classification",
        json={"tagName": "Release QA", "subtagName": "Deletion"},
    ).status_code == 200
    assert client.get(f"/api/v1/articles/{article_id}").json()["operationSummary"]["captureCount"] == 1

    trashed = client.post(
        "/api/v1/articles/batch-delete",
        json={"articleIds": [article_id, second_id]},
    )

    assert trashed.status_code == 200
    assert {article["id"] for article in trashed.json()["articles"]} == {article_id, second_id}
    assert client.get("/api/v1/articles").json()["articles"] == []
    assert {article["id"] for article in client.get("/api/v1/trash/articles").json()["articles"]} == {article_id, second_id}

    restored = client.post(
        "/api/v1/trash/articles/batch",
        json={"articleIds": [article_id, second_id], "action": "restore"},
    )
    assert restored.status_code == 200
    assert {article["id"] for article in client.get("/api/v1/articles").json()["articles"]} == {article_id, second_id}

    assert client.delete(f"/api/v1/articles/{article_id}").status_code == 200
    deleted = client.delete(f"/api/v1/trash/articles/{article_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deletedArticleIds"] == [article_id]
    assert client.get(f"/api/v1/articles/{article_id}").status_code == 404
    assert client.get("/api/v1/trash/articles").json()["articles"] == []
    from src.core.activity import ArticleActivityStore
    from src.core.catalog import CatalogStore
    from src.core.trash import ArticleTrashStore

    assert CatalogStore().get_assignment(article_id) is None
    assert ArticleActivityStore().summary(article_id)["captureCount"] == 0
    assert ArticleTrashStore().get(article_id) is None


def test_failed_capture_job_can_be_retried_with_original_settings(web_client, monkeypatch) -> None:
    client, _, _ = web_client
    original = {
        "id": "failed-capture",
        "kind": "capture",
        "url": "https://example.com/retry",
        "status": "failed",
        "reviewMode": "ai_then_manual",
        "perspective": "original",
        "outputLanguage": "zh-CN",
        "createdAt": "2026-07-26T00:00:00+00:00",
        "error": "network unavailable",
        "events": [],
    }
    _capture_jobs[original["id"]] = original
    captured: dict[str, object] = {}

    async def fake_start(url: str, **settings):
        captured.update(url=url, **settings)
        job = {
            **original,
            "id": "retry-capture",
            "status": "queued",
            "error": None,
        }
        _capture_jobs[job["id"]] = job
        return job

    monkeypatch.setattr("src.api.web.start_capture_job", fake_start)

    response = client.post("/api/v1/captures/failed-capture/retry")

    assert response.status_code == 202
    assert response.json()["retryOfJobId"] == "failed-capture"
    assert original["retriedByJobId"] == "retry-capture"
    assert captured == {
        "url": "https://example.com/retry",
        "review_mode": "ai_then_manual",
        "perspective": "original",
        "output_language": "zh-CN",
    }


def test_article_detail_hides_stale_unreferenced_asset_files(web_client) -> None:
    client, config_path, article_id = web_client
    stale = config_path.parent / "articles" / article_id / "assets" / "stale.png"
    stale.write_bytes(b"old capture")

    detail = client.get(f"/api/v1/articles/{article_id}").json()

    assert [asset["name"] for asset in detail["assets"]] == ["image.png"]
    assert "stale.png" not in detail["displayMarkdown"]


def test_article_display_keeps_image_outside_complete_metadata_block(web_client) -> None:
    client, config_path, article_id = web_client
    article_dir = config_path.parent / "articles" / article_id
    source = """# Raw

> Source: [https://mp.weixin.qq.com/s/example](https://mp.weixin.qq.com/s/example)
> Platform: WeChat
> Author: Lin
> Published: 2026-07-01
> Captured: 2026-07-20T08:00:00+00:00
> Type: article

---

![Cover](assets/image.png)

Raw body.
"""
    malformed = """# Reviewed

> Source: [https://mp.weixin.qq.com/s/example](https://mp.weixin.qq.com/s/example)
> Platform: WeChat
> Author: Lin
> Published: 2026-07-01
> Captured: 2026-07-20T08:00:00+00:00

![Cover](assets/image.png)

> Type: article

---

## AI Summary

Summary.
"""
    (article_dir / "raw.md").write_text(source, encoding="utf-8")
    (article_dir / "reviewed.md").write_text(malformed, encoding="utf-8")

    detail = client.get(f"/api/v1/articles/{article_id}")

    assert detail.status_code == 200
    display = detail.json()["displayMarkdown"]
    assert display.count("> Type: article") == 1
    assert display.index("> Captured:") < display.index("> Type: article")
    assert display.index("> Type: article") < display.index("---")
    assert display.index("---") < display.index("assets/image.png")
    assert display.index("assets/image.png") < display.index("## AI Summary")


def test_markdown_metadata_accepts_bold_field_names(web_client) -> None:
    client, config_path, article_id = web_client
    article_dir = config_path.parent / "articles" / article_id
    manifest = json.loads((article_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["article"].pop("author", None)
    manifest["article"].pop("published_at", None)
    (article_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    markdown = "# Article\n\n> **Author**: Ada Lovelace\n> **Published**: 2026-07-22\n"
    (article_dir / "reviewed.md").write_text(markdown, encoding="utf-8")

    detail = client.get(f"/api/v1/articles/{article_id}").json()
    assert detail["author"] == "Ada Lovelace"
    assert detail["publishedAt"] == "2026-07-22"


def test_article_detail_recovers_active_review_and_reuses_it(web_client) -> None:
    client, _, article_id = web_client
    active_job = {
        "id": "active-review-job",
        "articleId": article_id,
        "perspective": "original",
        "status": "running",
        "stage": "ai_review",
        "progress": 42,
        "createdAt": "2026-07-22T00:00:00+00:00",
        "startedAt": "2026-07-22T00:00:01+00:00",
        "finishedAt": None,
        "reviewPreview": "partial",
        "events": [],
        "error": None,
    }
    _review_jobs[active_job["id"]] = active_job

    detail = client.get(f"/api/v1/articles/{article_id}")
    repeated = client.post(
        f"/api/v1/articles/{article_id}/review",
        json={"perspective": "original"},
    )

    assert detail.status_code == 200
    assert detail.json()["activeReview"]["id"] == active_job["id"]
    assert repeated.status_code == 202
    assert repeated.json()["id"] == active_job["id"]
    assert len(_review_jobs) == 1


def test_frontend_client_routes_serve_spa_entry(web_client) -> None:
    client, _, article_id = web_client
    assert client.get("/app/settings").status_code == 200
    assert client.get(f"/app/articles/{article_id}").status_code == 200

    asset = client.get(f"/api/v1/articles/{article_id}/assets/image.png")
    assert asset.status_code == 200
    assert asset.content == b"not-a-real-png"


def test_article_can_be_assigned_to_two_level_taxonomy(web_client) -> None:
    client, _, article_id = web_client

    assigned = client.patch(
        f"/api/v1/articles/{article_id}/classification",
        json={
            "tagName": "AI",
            "tagDescription": "Artificial intelligence",
            "subtagName": "Agent",
            "subtagDescription": "Autonomous AI systems",
        },
    )

    assert assigned.status_code == 200
    assert assigned.json()["tag_name"] == "AI"
    assert assigned.json()["subtag_name"] == "Agent"
    taxonomy = client.get("/api/v1/taxonomy").json()["tags"]
    assert taxonomy[0]["name"] == "AI"
    assert taxonomy[0]["children"][0]["name"] == "Agent"
    detail = client.get(f"/api/v1/articles/{article_id}").json()
    assert detail["classification"]["subtag_name"] == "Agent"


def test_web_mcp_and_cli_share_canonical_taxonomy_ids(web_client, capsys) -> None:
    client, _, article_id = web_client
    from src.cli import _main_async, parse_args
    from src.mcp.server import classify_article as mcp_classify_article

    web_assignment = client.patch(
        f"/api/v1/articles/{article_id}/classification",
        json={
            "tagName": "AI",
            "tagDescription": "Artificial intelligence",
            "subtagName": "Agents",
            "subtagDescription": "Autonomous AI systems",
            "tagLocalizations": {
                "en-US": {"name": "AI", "description": "Artificial intelligence", "aliases": ["Artificial Intelligence"]},
                "zh-CN": {"name": "人工智能", "description": "人工智能相关内容", "aliases": ["AI"]},
            },
            "subtagLocalizations": {
                "en-US": {"name": "Agents", "description": "Autonomous AI systems", "aliases": ["AI Agent"]},
                "zh-CN": {"name": "智能体", "description": "自主智能系统", "aliases": ["Agent"]},
            },
        },
    ).json()

    mcp_result = asyncio.run(
        mcp_classify_article(
            article_id,
            tag_id=web_assignment["tag_id"],
            subtag_id=web_assignment["subtag_id"],
            locale="en-US",
        )
    )
    assert mcp_result["classification"]["tag_id"] == web_assignment["tag_id"]
    assert mcp_result["classification"]["subtag_id"] == web_assignment["subtag_id"]

    exit_code = asyncio.run(_main_async(parse_args([
        "taxonomy", "move", article_id,
        "--tag-id", web_assignment["tag_id"],
        "--subtag-id", web_assignment["subtag_id"],
        "--locale", "zh-CN",
        "--json",
    ])))
    assert exit_code == 0
    cli_payload = json.loads(capsys.readouterr().out)
    assert cli_payload["classification"]["tag_id"] == web_assignment["tag_id"]
    assert cli_payload["classification"]["subtag_id"] == web_assignment["subtag_id"]

    chinese = client.get(f"/api/v1/articles/{article_id}?locale=zh-CN").json()["classification"]
    assert chinese["tag_name"] == "人工智能"
    assert chinese["subtag_name"] == "智能体"


def test_taxonomy_localizes_and_merges_aliases(web_client) -> None:
    client, _, article_id = web_client
    from src.core.catalog import CatalogStore

    store = CatalogStore()
    first = store.assign(
        article_id,
        tag_name="AI Agents",
        locale="en-US",
        tag_localizations={
            "en-US": {"name": "AI Agents", "description": "Autonomous AI systems and workflows.", "aliases": ["Agents"]},
            "zh-CN": {"name": "智能体", "description": "自主智能系统及其工作流。", "aliases": ["AI 智能体"]},
        },
    )
    second = store.assign(
        "another-article",
        tag_name="Agents",
        locale="en-US",
        tag_localizations={
            "en-US": {"name": "Agents", "description": "", "aliases": ["AI Agents"]},
            "zh-CN": {"name": "智能体", "description": "", "aliases": []},
        },
    )

    assert first["tag_id"] == second["tag_id"]
    english = client.get("/api/v1/taxonomy?locale=en-US").json()["tags"][0]
    chinese = client.get("/api/v1/taxonomy?locale=zh-CN").json()["tags"][0]
    assert english["name"] == "AI Agents"
    assert "Agents" in english["aliases"]
    assert chinese["name"] == "智能体"
    assert chinese["description"] == "自主智能系统及其工作流。"


def test_pipeline_defaults_are_localized_and_read_only(web_client) -> None:
    client, _, _ = web_client
    english = client.get("/api/v1/pipeline/settings?locale=en-US").json()
    chinese = client.get("/api/v1/pipeline/settings?locale=zh-CN").json()

    assert english["perspectives"][0]["label"] == "Source-faithful"
    assert chinese["perspectives"][0]["label"] == "基于原文"
    assert english["perspectives"][0]["editable"] is False
    assert english["commonEditable"] is False


def test_pipeline_can_create_update_and_remove_custom_perspective(web_client) -> None:
    client, config_path, _ = web_client
    payload = client.get("/api/v1/pipeline/settings?locale=zh-CN").json()
    custom = dict(payload["perspectives"][0])
    custom.update({
        "id": "custom_reader",
        "label": "研究视角",
        "description": "突出证据与限制条件。",
        "prompt": "请从研究者角度分析证据、方法和限制。",
        "builtin": False,
        "editable": True,
    })
    payload["perspectives"].append(custom)
    payload["activePerspective"] = "custom_reader"

    created = client.patch("/api/v1/pipeline/settings?locale=zh-CN", json=payload)

    assert created.status_code == 200, created.text
    created_item = next(item for item in created.json()["perspectives"] if item["id"] == "custom_reader")
    assert created_item["editable"] is True
    assert created_item["prompt"] == custom["prompt"]
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    profile = persisted["pipeline"]["perspectives"]["custom_reader"]
    assert Path(profile["prompt_path"]).read_text(encoding="utf-8") == custom["prompt"]
    assert Path(profile["template_path"]).is_file()

    remove_payload = created.json()
    remove_payload["activePerspective"] = "original"
    remove_payload["perspectives"] = [item for item in remove_payload["perspectives"] if item["id"] != "custom_reader"]
    removed = client.patch("/api/v1/pipeline/settings?locale=zh-CN", json=remove_payload)

    assert removed.status_code == 200, removed.text
    assert all(item["id"] != "custom_reader" for item in removed.json()["perspectives"])
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert "custom_reader" not in persisted["pipeline"]["perspectives"]


def test_article_operation_counts_are_exposed(web_client) -> None:
    client, _, article_id = web_client
    from src.core.activity import ArticleActivityStore

    store = ArticleActivityStore()
    store.record(article_id, "review", outputLanguage="en-US")
    store.record(article_id, "review", outputLanguage="zh-CN")
    store.record(article_id, "upload", target="siyuan")

    operations = client.get(f"/api/v1/articles/{article_id}").json()["operationSummary"]
    assert operations["reviewCount"] == 2
    assert operations["rereviewCount"] == 1
    assert operations["uploadCount"] == 1


def test_settings_api_masks_and_preserves_secrets(web_client) -> None:
    client, config_path, _ = web_client
    settings = client.get("/api/v1/settings")
    assert settings.status_code == 200
    assert settings.json()["apiKeyConfigured"] is True
    assert "existing-secret" not in settings.text
    assert "firecrawl-secret" not in settings.text
    assert "siyuan-secret" not in settings.text

    payload = settings.json()
    payload["aiProviders"][0]["model"] = "updated-model"
    response = client.patch("/api/v1/settings", json=payload)
    assert response.status_code == 200
    assert response.json()["model"] == "updated-model"
    assert "existing-secret" not in response.text

    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["ai_providers"]["openai"]["api_key"] == "existing-secret"
    assert persisted["ai_providers"]["openai"]["model"] == "updated-model"

    reloaded = client.get("/api/v1/settings").json()
    assert reloaded["aiProviders"][0]["model"] == "updated-model"
    assert "existing-secret" not in json.dumps(reloaded)


def test_settings_infers_legacy_provider_types(web_client) -> None:
    client, _, _ = web_client

    providers = {
        provider["name"]: provider["providerType"]
        for provider in client.get("/api/v1/settings").json()["aiProviders"]
    }

    assert providers["openai"] == "custom"
    assert providers["Kimi Backup"] == "kimi"
    assert providers["MiniMax Backup"] == "minimax"
    assert providers["GLM Backup"] == "zhipu"
    assert providers["Doubao Work"] == "volcengine"


def test_settings_support_named_providers_and_distinct_fallback(web_client) -> None:
    client, config_path, _ = web_client
    payload = client.get("/api/v1/settings").json()
    payload["aiProvider"] = "My Gateway"
    payload["aiProviders"].append({
        "name": "My Gateway",
        "providerType": "custom",
        "apiFormat": "openai_chat",
        "model": "deepseek-v4-pro",
        "apiBase": "https://model-api.example.test",
        "apiKey": "custom-secret",
        "apiKeyConfigured": False,
    })
    payload["crawlerPrimary"] = "firecrawl"
    payload["crawlerFallback"] = "firecrawl"

    response = client.patch("/api/v1/settings", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["aiProvider"] == "My Gateway"
    assert body["crawlerPrimary"] == "firecrawl"
    assert body["crawlerFallback"] == "crawl4ai"
    assert "custom-secret" not in response.text
    custom = next(provider for provider in body["aiProviders"] if provider["name"] == "My Gateway")
    assert custom["apiFormat"] == "openai_chat"
    assert custom["providerType"] == "custom"
    assert custom["apiKeyConfigured"] is True

    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["ai_providers"]["My Gateway"]["api_key"] == "custom-secret"
    assert persisted["ai_providers"]["My Gateway"]["provider_type"] == "custom"
    assert persisted["ai_providers"]["Kimi Backup"]["provider_type"] == "kimi"
    assert persisted["crawler"]["fallback"] == "crawl4ai"


def test_settings_delete_provider_removes_persisted_profile(web_client) -> None:
    client, config_path, _ = web_client
    payload = client.get("/api/v1/settings").json()
    payload["aiProviders"] = [provider for provider in payload["aiProviders"] if provider["name"] != "Kimi Backup"]

    response = client.patch("/api/v1/settings", json=payload)

    assert response.status_code == 200
    assert all(provider["name"] != "Kimi Backup" for provider in response.json()["aiProviders"])
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert "Kimi Backup" not in persisted["ai_providers"]


def test_settings_normalizes_active_provider_name_case(web_client) -> None:
    client, config_path, _ = web_client
    payload = client.get("/api/v1/settings").json()
    payload["aiProvider"] = "KIMI BACKUP"

    response = client.patch("/api/v1/settings", json=payload)

    assert response.status_code == 200
    assert response.json()["aiProvider"] == "Kimi Backup"
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["ai"]["provider"] == "Kimi Backup"


def test_active_provider_endpoint_persists_provider_and_model_across_reload(web_client) -> None:
    client, config_path, _ = web_client
    settings = client.get("/api/v1/settings").json()
    kimi = next(provider for provider in settings["aiProviders"] if provider["name"] == "Kimi Backup")
    kimi["model"] = "kimi-model-after-switch"

    response = client.patch(
        "/api/v1/settings/active-provider",
        json={"providerName": "KIMI BACKUP", "settings": settings},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["aiProvider"] == "Kimi Backup"
    assert response.json()["model"] == "kimi-model-after-switch"

    clear_config_cache()
    effective = load_config().resolve_ai_settings()
    assert effective["provider"] == "Kimi Backup"
    assert effective["model"] == "kimi-model-after-switch"
    reloaded = client.get("/api/v1/settings")
    assert reloaded.headers["cache-control"] == "no-store"
    assert reloaded.json()["aiProvider"] == "Kimi Backup"
    assert reloaded.json()["model"] == "kimi-model-after-switch"

    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["ai"]["provider"] == "Kimi Backup"
    assert persisted["ai_providers"]["Kimi Backup"]["model"] == "kimi-model-after-switch"


def test_active_provider_endpoint_saves_vision_role_for_current_provider(web_client) -> None:
    client, config_path, _ = web_client
    settings = client.get("/api/v1/settings").json()
    current = next(provider for provider in settings["aiProviders"] if provider["name"] == "openai")
    current["visionCapable"] = True
    settings["imageProvider"] = "openai"

    response = client.patch(
        "/api/v1/settings/active-provider",
        json={"providerName": "openai", "settings": settings},
    )

    assert response.status_code == 200, response.text
    assert response.json()["imageProvider"] == "openai"
    assert next(provider for provider in response.json()["aiProviders"] if provider["name"] == "openai")["visionCapable"] is True
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["ai"]["image_provider"] == "openai"
    assert persisted["ai_providers"]["openai"]["vision_capable"] is True


def test_active_provider_endpoint_rejects_missing_provider(web_client) -> None:
    client, _, _ = web_client
    settings = client.get("/api/v1/settings").json()

    response = client.patch(
        "/api/v1/settings/active-provider",
        json={"providerName": "Missing Provider", "settings": settings},
    )

    assert response.status_code == 400
    assert "Missing Provider" in response.json()["error"]


@pytest.mark.parametrize(
    ("payload", "expected_secret"),
    [
        ({"service": "ai", "providerName": "openai"}, "existing-secret"),
        ({"service": "firecrawl"}, "firecrawl-secret"),
        ({"service": "siyuan"}, "siyuan-secret"),
    ],
)
def test_settings_secret_reveal_is_explicit_and_not_cached(web_client, payload, expected_secret) -> None:
    client, _, _ = web_client

    response = client.post("/api/v1/settings/secrets/reveal", json=payload)

    assert response.status_code == 200
    assert response.json()["secret"] == expected_secret
    assert response.headers["cache-control"] == "no-store"


def test_settings_secret_reveal_rejects_remote_host_unless_enabled(web_client, monkeypatch) -> None:
    client, _, _ = web_client
    payload = {"service": "ai", "providerName": "openai"}

    rejected = client.post(
        "/api/v1/settings/secrets/reveal",
        json=payload,
        headers={"host": "noosphere.example"},
    )
    assert rejected.status_code == 403
    assert rejected.headers["cache-control"] == "no-store"
    assert "existing-secret" not in rejected.text

    monkeypatch.setenv("NOOSPHERE_ALLOW_REMOTE_SECRET_REVEAL", "true")
    allowed = client.post(
        "/api/v1/settings/secrets/reveal",
        json=payload,
        headers={"host": "noosphere.example"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["secret"] == "existing-secret"


def test_provider_connection_test_uses_draft_without_persisting(web_client, monkeypatch) -> None:
    client, config_path, _ = web_client
    payload = client.get("/api/v1/settings").json()
    payload["aiProviders"][0]["model"] = "draft-only-model"

    async def fake_generate(self, system_prompt: str, user_prompt: str):
        assert self.settings.model == "draft-only-model"
        return SimpleNamespace(text="NOOSPHERE_OK", model=self.settings.model)

    monkeypatch.setattr("src.integrations.ai_client.AIClient.generate_text", fake_generate)
    response = client.post("/api/v1/settings/test", json={"service": "ai", "providerName": "openai", "settings": payload})

    assert response.status_code == 200
    assert response.json()["model"] == "draft-only-model"
    assert json.loads(config_path.read_text(encoding="utf-8"))["ai_providers"]["openai"]["model"] == "test-model"


def test_article_can_be_re_reviewed_from_current_reviewed_markdown(web_client, monkeypatch) -> None:
    client, config_path, article_id = web_client
    reviewed_path = config_path.parent / "articles" / article_id / "reviewed.md"
    reviewed_path.write_text("# Manually edited\n\nKeep this version.\n", encoding="utf-8")
    _capture_jobs["failed-capture"] = {
        "id": "failed-capture",
        "kind": "capture",
        "articleId": article_id,
        "status": "failed",
        "createdAt": "2026-07-23T00:00:00+00:00",
        "events": [],
        "error": "Provider rejected the original request",
    }

    async def fake_review(path: Path, *, perspective: str, source_markdown: str, output_language: str):
        assert path == reviewed_path
        assert perspective == "original"
        assert source_markdown.startswith("# Manually edited")
        path.write_text("# AI reviewed\n\nRewritten.\n", encoding="utf-8")
        return SimpleNamespace(ok=True, issues=[])

    async def fake_classify(classified_article_id: str, path: Path, locale: str):
        assert classified_article_id == article_id
        return {"tag_name": "AI", "subtag_name": None}

    monkeypatch.setattr("src.graph.graph.run_ai_review_graph", fake_review)
    monkeypatch.setattr("src.core.catalog.classify_reviewed_article", fake_classify)
    response = client.post(f"/api/v1/articles/{article_id}/review", json={"perspective": "original"})
    assert response.status_code == 202

    job = response.json()
    deadline = time.monotonic() + 1
    while job["status"] not in {"succeeded", "failed"} and time.monotonic() < deadline:
        job = client.get(f"/api/v1/reviews/{job['id']}").json()
        time.sleep(0.01)

    assert job["status"] == "succeeded"
    assert job["progress"] == 100
    assert reviewed_path.read_text(encoding="utf-8").startswith("# AI reviewed")
    recovered = client.get("/api/v1/captures").json()["jobs"][0]
    assert recovered["status"] == "recovered"
    assert recovered["error"] is None
    assert recovered["originalError"] == "Provider rejected the original request"
    assert recovered["recoveredByReviewJobId"] == job["id"]
    assert recovered["events"][-1]["message"] == "pipeline.events.recoveredByReview"


def test_capture_ai_then_manual_runs_review_and_pauses(web_client, monkeypatch) -> None:
    client, config_path, article_id = web_client
    reviewed_path = config_path.parent / "articles" / article_id / "reviewed.md"

    async def fake_extract(url: str):
        assert url == "https://example.com/article"
        return reviewed_path

    async def fake_review(path: Path, *, perspective: str, output_language: str):
        assert path == reviewed_path
        assert perspective == "original"
        return SimpleNamespace(ok=True, issues=[])

    async def fake_classify(classified_article_id: str, path: Path, locale: str):
        assert classified_article_id == article_id
        assert path == reviewed_path
        return {"tag_name": "AI", "subtag_name": "Agent"}

    monkeypatch.setattr("src.graph.graph.run_extract_graph", fake_extract)
    monkeypatch.setattr("src.graph.graph.run_ai_review_graph", fake_review)
    monkeypatch.setattr("src.core.catalog.classify_reviewed_article", fake_classify)
    response = client.post("/api/v1/captures", json={"url": "https://example.com/article", "reviewMode": "ai_then_manual", "perspective": "original"})
    assert response.status_code == 202

    deadline = time.monotonic() + 1
    job = response.json()
    while job["status"] not in {"awaiting_review", "failed"} and time.monotonic() < deadline:
        job = client.get("/api/v1/captures").json()["jobs"][0]
        time.sleep(0.01)

    assert job["status"] == "awaiting_review"
    assert job["reviewMode"] == "ai_then_manual"
    assert job["articleId"] == article_id
    assert job["events"]


def test_capture_waits_for_human_review_by_default(web_client, monkeypatch) -> None:
    client, config_path, article_id = web_client
    reviewed_path = config_path.parent / "articles" / article_id / "reviewed.md"

    async def fake_extract(url: str):
        return reviewed_path

    async def fake_review(path: Path, *, perspective: str, output_language: str):
        return SimpleNamespace(ok=True, issues=[])

    async def fake_classify(classified_article_id: str, path: Path, locale: str):
        return {"tag_name": "AI", "subtag_name": None}

    monkeypatch.setattr("src.graph.graph.run_extract_graph", fake_extract)
    monkeypatch.setattr("src.graph.graph.run_ai_review_graph", fake_review)
    monkeypatch.setattr("src.core.catalog.classify_reviewed_article", fake_classify)
    response = client.post("/api/v1/captures", json={"url": "https://example.com/article"})

    deadline = time.monotonic() + 1
    job = response.json()
    while job["status"] not in {"awaiting_review", "failed"} and time.monotonic() < deadline:
        job = client.get("/api/v1/captures").json()["jobs"][0]
        time.sleep(0.01)

    assert job["status"] == "awaiting_review"
    assert job["reviewMode"] == "ai_then_manual"


def test_capture_auto_upload_runs_without_human_checkpoint(web_client, monkeypatch) -> None:
    client, config_path, article_id = web_client
    reviewed_path = config_path.parent / "articles" / article_id / "reviewed.md"

    async def fake_extract(url: str):
        return reviewed_path

    async def fake_review(path: Path, *, perspective: str, output_language: str):
        return SimpleNamespace(ok=True, issues=[])

    async def fake_classify(classified_article_id: str, path: Path, locale: str):
        return {"tag_name": "AI", "subtag_name": None}

    async def fake_upload(path: Path, target: str):
        assert path == reviewed_path
        assert target == "siyuan"
        return SimpleNamespace(hpath="/Noosphere/Article", created=True)

    monkeypatch.setattr("src.graph.graph.run_extract_graph", fake_extract)
    monkeypatch.setattr("src.graph.graph.run_ai_review_graph", fake_review)
    monkeypatch.setattr("src.graph.graph.run_upload_graph", fake_upload)
    monkeypatch.setattr("src.core.catalog.classify_reviewed_article", fake_classify)
    response = client.post(
        "/api/v1/captures?locale=en-US",
        json={"url": "https://example.com/automatic", "reviewMode": "auto_upload", "perspective": "original", "outputLanguage": "follow_ui"},
    )

    deadline = time.monotonic() + 1
    job = response.json()
    while job["status"] not in {"succeeded", "failed"} and time.monotonic() < deadline:
        job = client.get("/api/v1/captures").json()["jobs"][0]
        time.sleep(0.01)

    assert job["status"] == "succeeded"
    assert job["outputLanguage"] == "en-US"
    assert job["result"] == {"hpath": "/Noosphere/Article", "created": True}


def test_capture_manual_only_is_rejected(web_client, monkeypatch) -> None:
    client, config_path, article_id = web_client
    reviewed_path = config_path.parent / "articles" / article_id / "reviewed.md"

    response = client.post(
        "/api/v1/captures",
        json={"url": "https://example.com/manual", "reviewMode": "manual_only"},
    )

    assert response.status_code == 400
    assert "Unsupported review mode" in response.json()["error"]


def test_article_reviewed_markdown_can_be_saved_and_uploaded(web_client, monkeypatch) -> None:
    client, _, article_id = web_client
    saved = client.patch(
        f"/api/v1/articles/{article_id}",
        json={"reviewedMarkdown": "# Edited\n\n`inline`\n"},
    )
    assert saved.status_code == 200
    assert client.get(f"/api/v1/articles/{article_id}").json()["reviewedMarkdown"] == "# Edited\n\n`inline`\n"

    async def fake_upload(path: Path, target: str):
        assert path.name == "reviewed.md"
        assert target == "siyuan"
        return SimpleNamespace(hpath="/Noosphere/Edited", created=False)

    monkeypatch.setattr("src.graph.graph.run_upload_graph", fake_upload)
    uploaded = client.post(f"/api/v1/articles/{article_id}/upload", json={"target": "siyuan"})
    assert uploaded.status_code == 202
    job = uploaded.json()
    deadline = time.monotonic() + 1
    while job["status"] not in {"succeeded", "failed"} and time.monotonic() < deadline:
        job = client.get(f"/api/v1/uploads/{job['id']}").json()
        time.sleep(0.01)
    assert job["status"] == "succeeded"
    assert job["progress"] == 100
    assert job["result"] == {"created": False}


def test_article_image_can_be_removed_and_restored_without_mutating_raw(web_client) -> None:
    client, _, article_id = web_client
    article_url = f"/api/v1/articles/{article_id}"
    initial = client.get(article_url).json()
    raw_before = initial["rawMarkdown"]

    removed = client.patch(
        f"{article_url}/images/image.png",
        json={"state": "removed", "reviewedMarkdown": initial["displayMarkdown"]},
    )
    assert removed.status_code == 200
    detail = client.get(article_url).json()
    assert detail["rawMarkdown"] == raw_before
    assert "assets/image.png" not in detail["reviewedMarkdown"]
    assert "/removed/image.png?state=removed" in detail["displayMarkdown"]
    assert detail["removedAssets"][0]["source"] == "manual"
    assert client.get(f"{article_url}/assets/image.png").status_code == 404
    assert client.get(f"{article_url}/removed/image.png").status_code == 200

    restored = client.patch(
        f"{article_url}/images/image.png",
        json={"state": "active", "reviewedMarkdown": detail["displayMarkdown"]},
    )
    assert restored.status_code == 200
    detail = client.get(article_url).json()
    assert detail["removedAssets"] == []
    assert "assets/image.png" in detail["reviewedMarkdown"]
    assert client.get(f"{article_url}/assets/image.png").status_code == 200


def test_mcp_and_cli_share_article_image_state(web_client, capsys) -> None:
    client, _, article_id = web_client
    from src.cli import _main_async, parse_args
    from src.mcp.server import set_article_image_state as mcp_set_article_image_state

    removed = asyncio.run(mcp_set_article_image_state(article_id, "image.png", "removed"))
    assert removed["state"] == "removed"
    detail = client.get(f"/api/v1/articles/{article_id}").json()
    assert detail["assets"] == []
    assert detail["removedAssets"][0]["name"] == "image.png"

    exit_code = asyncio.run(_main_async(parse_args([
        "images", "set", article_id, "image.png",
        "--state", "active",
        "--json",
    ])))
    assert exit_code == 0
    cli_payload = json.loads(capsys.readouterr().out)
    assert cli_payload["state"] == "active"
    restored = client.get(f"/api/v1/articles/{article_id}").json()
    assert restored["removedAssets"] == []
    assert restored["assets"][0]["name"] == "image.png"


def test_unified_job_endpoints_cover_all_background_kinds(web_client) -> None:
    client, _, article_id = web_client
    _capture_jobs["capture-1"] = {
        "id": "capture-1",
        "kind": "capture",
        "articleId": article_id,
        "status": "running",
        "createdAt": "2026-07-22T00:00:00+00:00",
    }
    _review_jobs["review-1"] = {
        "id": "review-1",
        "kind": "review",
        "articleId": article_id,
        "status": "succeeded",
        "createdAt": "2026-07-22T00:00:01+00:00",
    }

    all_jobs = client.get("/api/v1/jobs").json()
    capture_jobs = client.get("/api/v1/jobs?kind=capture").json()
    one_job = client.get("/api/v1/jobs/review-1").json()

    assert {job["id"] for job in all_jobs["jobs"]} == {"capture-1", "review-1"}
    assert [job["id"] for job in capture_jobs["jobs"]] == ["capture-1"]
    assert one_job["id"] == "review-1"
    assert one_job["kind"] == "review"


def test_capture_rejects_non_http_url(web_client) -> None:
    client, _, _ = web_client
    response = client.post("/api/v1/captures", json={"url": "file:///etc/passwd"})
    assert response.status_code == 400
