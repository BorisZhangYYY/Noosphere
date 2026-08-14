"""Tests for per-article reflections and AI polish."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.reflection import (
    merge_reflection,
    read_reflection,
    read_upload_enabled,
    reflection_heading,
    set_upload_enabled,
    write_reflection,
)


def _write_test_config(monkeypatch, tmp_path: Path) -> Path:
    from src.core.config.config import clear_config_cache

    data_dir = tmp_path / ".noosphere"
    output_dir = data_dir / "articles"
    config_path = data_dir / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "ai": {"provider": "openai"},
                "ai_providers": {
                    "openai": {
                        "api_format": "openai_chat",
                        "model": "active-model",
                        "api_base": "https://api.example.test/v1",
                        "api_key": "test-key",
                    }
                },
                "checkpoint": {"backend": "memory"},
                "local_archive": {
                    "enabled": True,
                    "output_dir": str(data_dir / "archive"),
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NOOSPHERE_HOME", str(data_dir))
    monkeypatch.setenv("NOOSPHERE_CONFIG", str(config_path))
    monkeypatch.setenv("NOOSPHERE_OUTPUT_DIR", str(output_dir))
    clear_config_cache()
    return output_dir


def _article_workspace(output_dir: Path, article_id: str = "wechat_mp_example_12345678") -> Path:
    article_dir = output_dir / article_id
    (article_dir / "assets").mkdir(parents=True)
    (article_dir / "raw.md").write_text("# Raw\n\nBody.\n", encoding="utf-8")
    (article_dir / "reviewed.md").write_text("# Reviewed\n\nBody.\n", encoding="utf-8")
    (article_dir / "manifest.json").write_text(
        json.dumps(
            {
                "article_id": article_id,
                "article": {
                    "platform": "wechat_mp",
                    "platform_label": "WeChat",
                    "url": "https://example.test/article",
                    "title": "Reviewed",
                    "content_type": "article",
                },
                "paths": {"raw": "raw.md", "reviewed": "reviewed.md", "assets": "assets"},
            }
        ),
        encoding="utf-8",
    )
    return article_dir


def test_reflection_storage_heading_and_merge(tmp_path: Path) -> None:
    article_dir = tmp_path / "article"
    assert reflection_heading("en-US") == "## My Reflections"
    assert reflection_heading("zh-CN") == "## 我的感悟"
    assert read_reflection(article_dir) == ""
    written = write_reflection(article_dir, "我的感悟。")
    assert written == article_dir / "reflection.md"
    assert read_reflection(article_dir) == "我的感悟。"
    assert merge_reflection("# Reviewed\n", "  \n") == "# Reviewed\n"
    assert merge_reflection("# Reviewed\n", "我的感悟。", "zh-CN") == (
        "# Reviewed\n\n---\n\n## 我的感悟\n\n我的感悟。\n"
    )


def test_upload_toggle_preserves_manifest_and_rejects_corruption(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text('{"article_id":"a1","article":{"title":"Keep"}}', encoding="utf-8")
    set_upload_enabled(manifest_path, True)
    assert read_upload_enabled(manifest_path) is True
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["article"]["title"] == "Keep"

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid"):
        set_upload_enabled(corrupt, True)
    assert corrupt.read_text(encoding="utf-8") == "{broken"


@pytest.mark.asyncio
async def test_polish_uses_review_model_and_falls_back_when_missing(monkeypatch, tmp_path: Path) -> None:
    output_dir = _write_test_config(monkeypatch, tmp_path)
    article_dir = _article_workspace(output_dir)
    (article_dir / "reflection.md").write_text("My thoughts.", encoding="utf-8")
    (article_dir / "review.json").write_text(
        json.dumps(
            {
                "status": "reviewed",
                "ai": {"rewrite_provider": "removed-provider", "rewrite_model": "old-model"},
            }
        ),
        encoding="utf-8",
    )

    from src.graph.graph import run_reflection_graph
    from src.integrations.ai_client import AIClient, AITextResponse

    captured: dict[str, str] = {}

    async def fake_generate(self, system_prompt: str, user_prompt: str) -> AITextResponse:
        captured["provider"] = self.settings.provider
        captured["model"] = self.settings.model
        captured["system_prompt"] = system_prompt
        captured["prompt"] = user_prompt
        return AITextResponse("Polished reflection.", self.settings.model, self.settings.provider)

    monkeypatch.setattr(AIClient, "generate_text", fake_generate)
    result = await run_reflection_graph(article_dir / "reviewed.md")
    assert result == {
        "markdown": "Polished reflection.",
        "model": "active-model",
        "provider": "openai",
    }
    assert captured["provider"] == "openai"
    assert "Markdown level 3 (`###`) or deeper" in captured["system_prompt"]
    assert "My thoughts." in captured["prompt"]
    assert read_reflection(article_dir) == "My thoughts."


@pytest.mark.asyncio
async def test_polish_prefers_recorded_review_model(monkeypatch, tmp_path: Path) -> None:
    output_dir = _write_test_config(monkeypatch, tmp_path)
    article_dir = _article_workspace(output_dir)
    write_reflection(article_dir, "My thoughts.")
    (article_dir / "review.json").write_text(
        json.dumps(
            {
                "status": "reviewed",
                "ai": {"rewrite_provider": "openai", "rewrite_model": "recorded-model"},
            }
        ),
        encoding="utf-8",
    )

    from src.graph.graph import run_reflection_graph
    from src.integrations.ai_client import AIClient, AITextResponse

    async def fake_generate(self, system_prompt: str, user_prompt: str) -> AITextResponse:
        return AITextResponse("Polished.", self.settings.model, self.settings.provider)

    monkeypatch.setattr(AIClient, "generate_text", fake_generate)
    result = await run_reflection_graph(article_dir / "reviewed.md")
    assert result["provider"] == "openai"
    assert result["model"] == "recorded-model"


@pytest.mark.asyncio
async def test_upload_includes_reflection_without_touching_reviewed(monkeypatch, tmp_path: Path) -> None:
    output_dir = _write_test_config(monkeypatch, tmp_path)
    article_dir = _article_workspace(output_dir)
    write_reflection(article_dir, "我的感悟。")
    set_upload_enabled(article_dir / "manifest.json", True)

    from src.graph.graph import run_upload_graph

    await run_upload_graph(article_dir / "reviewed.md", target="local")
    archived = list((tmp_path / ".noosphere" / "archive").rglob("reviewed.md"))
    assert len(archived) == 1
    assert "## 我的感悟" in archived[0].read_text(encoding="utf-8")
    assert (article_dir / "reviewed.md").read_text(encoding="utf-8") == "# Reviewed\n\nBody.\n"
    assert not list(article_dir.glob(".upload-merged-*.md"))


@pytest.mark.asyncio
async def test_upload_override_and_failure_cleanup(monkeypatch, tmp_path: Path) -> None:
    output_dir = _write_test_config(monkeypatch, tmp_path)
    article_dir = _article_workspace(output_dir)
    write_reflection(article_dir, "Reflection.")

    from src.core.upload.adapters.local_adapter import LocalAdapter
    from src.graph.graph import run_upload_graph

    async def fail_upload(self, path, title=None):
        assert "## My Reflections" in path.read_text(encoding="utf-8")
        raise RuntimeError("upload failed")

    monkeypatch.setattr(LocalAdapter, "upload", fail_upload)
    with pytest.raises(RuntimeError, match="upload failed"):
        await run_upload_graph(
            article_dir / "reviewed.md",
            target="local",
            include_reflection=True,
        )
    assert not list(article_dir.glob(".upload-merged-*.md"))
    assert (article_dir / "reviewed.md").read_text(encoding="utf-8") == "# Reviewed\n\nBody.\n"


@pytest.mark.asyncio
async def test_upload_can_exclude_persistently_enabled_reflection(monkeypatch, tmp_path: Path) -> None:
    output_dir = _write_test_config(monkeypatch, tmp_path)
    article_dir = _article_workspace(output_dir)
    write_reflection(article_dir, "Reflection.")
    set_upload_enabled(article_dir / "manifest.json", True)

    from src.core.upload.adapters.local_adapter import LocalAdapter
    from src.graph.graph import run_upload_graph

    captured: dict[str, str] = {}
    original_upload = LocalAdapter.upload

    async def capture_upload(self, path, title=None):
        captured["path"] = str(path)
        captured["markdown"] = path.read_text(encoding="utf-8")
        return await original_upload(self, path, title)

    monkeypatch.setattr(LocalAdapter, "upload", capture_upload)
    await run_upload_graph(
        article_dir / "reviewed.md",
        target="local",
        include_reflection=False,
    )
    assert captured["path"] == str(article_dir / "reviewed.md")
    assert "My Reflections" not in captured["markdown"]
    assert (article_dir / "reviewed.md").read_text(encoding="utf-8") == "# Reviewed\n\nBody.\n"


def test_service_saves_reflection_and_persistent_toggle(monkeypatch, tmp_path: Path) -> None:
    output_dir = _write_test_config(monkeypatch, tmp_path)
    article_dir = _article_workspace(output_dir)
    from src.application.service import get_reflection, save_reflection

    assert get_reflection(article_dir.name)["exists"] is False
    saved = save_reflection(article_dir.name, "Reflection.", upload_enabled=True)
    assert saved["markdown"] == "Reflection."
    assert saved["uploadEnabled"] is True


def test_service_rejects_oversized_reflection(monkeypatch, tmp_path: Path) -> None:
    output_dir = _write_test_config(monkeypatch, tmp_path)
    article_dir = _article_workspace(output_dir)
    from src.application.service import save_reflection

    with pytest.raises(ValueError, match="10 MB"):
        save_reflection(article_dir.name, "x" * (10 * 1024 * 1024 + 1))
