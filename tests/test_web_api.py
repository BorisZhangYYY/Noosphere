"""Tests for the HTTP API consumed by the web frontend."""
from __future__ import annotations

import json
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

    async def fake_review(path: Path, *, perspective: str, source_markdown: str):
        assert path == reviewed_path
        assert perspective == "original"
        assert source_markdown.startswith("# Manually edited")
        path.write_text("# AI reviewed\n\nRewritten.\n", encoding="utf-8")
        return SimpleNamespace(ok=True, issues=[])

    async def fake_classify(classified_article_id: str, path: Path):
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


def test_capture_ai_then_manual_runs_review_and_pauses(web_client, monkeypatch) -> None:
    client, config_path, article_id = web_client
    reviewed_path = config_path.parent / "articles" / article_id / "reviewed.md"

    async def fake_extract(url: str):
        assert url == "https://example.com/article"
        return reviewed_path

    async def fake_review(path: Path, *, perspective: str):
        assert path == reviewed_path
        assert perspective == "original"
        return SimpleNamespace(ok=True, issues=[])

    async def fake_classify(classified_article_id: str, path: Path):
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

    async def fake_review(path: Path, *, perspective: str):
        return SimpleNamespace(ok=True, issues=[])

    async def fake_classify(classified_article_id: str, path: Path):
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


def test_capture_manual_only_skips_ai_review(web_client, monkeypatch) -> None:
    client, config_path, article_id = web_client
    reviewed_path = config_path.parent / "articles" / article_id / "reviewed.md"

    async def fake_extract(url: str):
        assert url == "https://example.com/manual"
        return reviewed_path

    async def unexpected_review(*args, **kwargs):
        raise AssertionError("manual-only capture must not invoke AI review")

    monkeypatch.setattr("src.graph.graph.run_extract_graph", fake_extract)
    monkeypatch.setattr("src.graph.graph.run_ai_review_graph", unexpected_review)
    response = client.post(
        "/api/v1/captures",
        json={"url": "https://example.com/manual", "reviewMode": "manual_only"},
    )

    deadline = time.monotonic() + 1
    job = response.json()
    while job["status"] not in {"awaiting_review", "failed"} and time.monotonic() < deadline:
        job = client.get("/api/v1/captures").json()["jobs"][0]
        time.sleep(0.01)

    assert job["status"] == "awaiting_review"
    assert job["reviewMode"] == "manual_only"
    assert job["articleId"] == article_id


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


def test_capture_rejects_non_http_url(web_client) -> None:
    client, _, _ = web_client
    response = client.post("/api/v1/captures", json={"url": "file:///etc/passwd"})
    assert response.status_code == 400
