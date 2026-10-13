"""Tests for the LangGraph-based article pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.graph.graph import (
    _default_initial_state,
    build_ai_review_graph,
    build_extract_graph,
    build_pipeline_graph,
    build_reflection_graph,
    build_upload_graph,
    run_ai_review_graph,
    run_pipeline_graph,
)


@pytest.fixture
def initial_state():
    return _default_initial_state()


def test_default_initial_state_has_required_keys(initial_state):
    required_keys = {
        "article_id",
        "url",
        "platform",
        "platform_label",
        "content_type",
        "title",
        "source_language",
        "output_language",
        "article_author",
        "article_published_at",
        "output_dir",
        "reviewed_path",
        "assets_dir",
        "raw_markdown",
        "assets",
        "download_failed",
        "reviewed_markdown",
        "review_summary",
        "review_revision",
        "image_layout_result",
        "image_filter_result",
        "validation_result",
        "feedback",
        "attempts",
        "max_attempts",
        "human_approved",
        "review_model",
        "review_provider",
        "review_perspective",
        "metadata_enrichment_outcomes",
        "reflection_markdown",
        "polished_reflection",
        "reflect_model",
        "reflect_provider",
        "upload_target",
        "removed_files",
        "upload_result",
        "upload_platform",
        "error",
        "status",
    }
    assert set(initial_state.keys()) == required_keys


@pytest.mark.parametrize(
    "builder",
    [
        build_extract_graph,
        build_ai_review_graph,
        build_reflection_graph,
        build_upload_graph,
        build_pipeline_graph,
    ],
)
def test_graph_compiles(builder):
    graph = builder().compile(checkpointer=MemorySaver())
    assert graph is not None


@pytest.mark.asyncio
async def test_pipeline_graph_sets_review_perspective(monkeypatch, tmp_path: Path) -> None:
    received: dict[str, object] = {}

    class FakeGraph:
        async def ainvoke(self, state, config):
            received.update(state=state, config=config)
            return {"upload_result": object()}

    class FakeBuilder:
        def compile(self, *, checkpointer):
            received["checkpointer"] = checkpointer
            return FakeGraph()

    async def fake_checkpointer():
        async def close():
            received["closed"] = True

        return object(), close

    monkeypatch.setattr("src.graph.graph.build_pipeline_graph", lambda: FakeBuilder())
    monkeypatch.setattr("src.graph.graph._get_checkpointer", fake_checkpointer)

    result = await run_pipeline_graph(
        "https://example.com/article",
        tmp_path,
        auto_confirm=True,
        perspective="novice",
    )

    assert result is not None
    assert received["state"]["review_perspective"] == "novice"
    assert received["config"]["configurable"]["auto_confirm"] is True
    assert received["closed"] is True


@pytest.mark.asyncio
async def test_get_checkpointer_sqlite(monkeypatch, tmp_path):
    from src.core.config.config import load_config
    from src.graph.graph import _get_checkpointer

    config = load_config()
    monkeypatch.setattr(config.checkpoint, "backend", "sqlite")
    monkeypatch.setattr(config.checkpoint, "sqlite_path", str(tmp_path / "test.sqlite"))

    saver, close_cb = await _get_checkpointer()
    try:
        assert isinstance(saver, AsyncSqliteSaver)
    finally:
        await close_cb()


@pytest.mark.asyncio
async def test_get_checkpointer_memory(monkeypatch):
    from src.core.config.config import load_config
    from src.graph.graph import _get_checkpointer

    config = load_config()
    monkeypatch.setattr(config.checkpoint, "backend", "memory")

    saver, close_cb = await _get_checkpointer()
    assert isinstance(saver, MemorySaver)
    # MemorySaver has no persistent state to clean up; close_cb is a no-op.


@pytest.mark.asyncio
async def test_ai_review_graph_matches_legacy_pipeline(monkeypatch, tmp_path):
    """Verify the new graph produces the same reviewed.md as the old pipeline."""
    import shutil

    from src.core.models.article import Article
    from src.core.paths.output_paths import article_output_paths
    from src.integrations.ai_client import AIClient, AITextResponse
    from src.pipelines.ai_review import run_ai_review

    url = "https://example.com/parity-test"
    article = Article(
        platform="test_platform",
        platform_label="Test Platform",
        url=url,
        title="Parity Test Article",
        markdown="This is the article body.\n\n![diagram](assets/image_01.png)\n",
        content_type="article",
        author="Test Author",
        published_at="2026-07-12",
    )

    paths = article_output_paths(tmp_path, article)
    paths.raw_path.parent.mkdir(parents=True, exist_ok=True)
    paths.asset_dir.mkdir(parents=True, exist_ok=True)
    (paths.asset_dir / "image_01.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    raw_markdown = article.to_review_markdown()
    paths.raw_path.write_text(raw_markdown, encoding="utf-8")
    shutil.copyfile(paths.raw_path, paths.reviewed_path)

    manifest = {
        "schema_version": 1,
        "article_id": paths.manifest_path.parent.name,
        "article": {
            "platform": article.platform,
            "platform_label": article.platform_label,
            "url": article.url,
            "title": article.title,
            "author": article.author,
            "published_at": article.published_at,
            "captured_at": article.captured_at,
            "status_code": article.status_code,
            "content_type": article.content_type,
            "extra": article.extra,
        },
        "paths": {
            "raw": "raw.md",
            "reviewed": "reviewed.md",
            "assets": "assets",
            "manifest": "manifest.json",
        },
        "assets": {"downloaded": [], "failed": {}},
    }
    paths.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    reviewed_markdown = (
        "# Parity Test Article\n\n"
        "> Source: [https://example.com/parity-test](https://example.com/parity-test)\n"
        "> Platform: Test Platform\n"
        "> Author: Test Author\n"
        "> Published: 2026-07-12\n"
        f"> Captured: {article.captured_at}\n"
        "> Type: article\n\n"
        "---\n\n"
        "## AI Summary\n\n"
        "A brief summary.\n\n"
        "---\n\n"
        "## Main Article\n\n"
        "This is the article body.\n\n"
        "![diagram](assets/image_01.png)\n"
    )

    async def mock_generate_text(self, system_prompt: str, user_prompt: str) -> AITextResponse:
        if "# Final image coordination protocol" in system_prompt:
            return AITextResponse(text=json.dumps({"images": [{"id": "image_001", "action": "keep"}], "text_edits": []}), model="mock", provider="mock")
        if "# Response protocol" in system_prompt:
            return AITextResponse(
                text=json.dumps({
                    "title": "Parity Test Article",
                    "summary": "A brief summary.",
                    "markdown": "## AI Summary\n\nA brief summary.\n\n---\n\n## Main Article\n\nThis is the article body.\n\n![diagram](assets/image_01.png)",
                    "metadata_candidates": {"author": None, "published_at": None},
                }),
                model="mock",
                provider="mock",
            )
        return AITextResponse(text=reviewed_markdown, model="mock", provider="mock")

    async def mock_generate_vision(self, system_prompt: str, content: list[dict]) -> AITextResponse:
        return AITextResponse(text=json.dumps({"classification": "RELEVANT", "description": "A diagram", "function": "Illustrates the explanation"}), model="mock", provider="mock")

    monkeypatch.setattr(AIClient, "generate_text", mock_generate_text)
    monkeypatch.setattr(AIClient, "generate_vision", mock_generate_vision)

    # Isolate the persistent image-filter cache to prevent test pollution.
    monkeypatch.setenv("NOOSPHERE_HOME", str(tmp_path / ".noosphere"))

    # Legacy pipeline
    legacy_result = await run_ai_review(paths.reviewed_path, max_attempts=1)
    legacy_reviewed = paths.reviewed_path.read_text(encoding="utf-8")

    # Reset reviewed.md to raw state for graph run
    shutil.copyfile(paths.raw_path, paths.reviewed_path)

    # Use in-memory checkpointer for parity test to avoid SQLite cleanup noise.
    from src.core.config.config import load_config
    config = load_config()
    monkeypatch.setattr(config.checkpoint, "backend", "memory")

    # New graph
    graph_result = await run_ai_review_graph(paths.reviewed_path, max_attempts=1)
    graph_reviewed = paths.reviewed_path.read_text(encoding="utf-8")

    assert legacy_result.ok, f"Legacy pipeline failed: {legacy_result.validation.issues}"
    assert graph_result.ok, f"Graph pipeline failed: {graph_result.issues}"
    assert legacy_reviewed == graph_reviewed


@pytest.mark.asyncio
async def test_review_graph_persists_evidence_backed_metadata_candidate(monkeypatch, tmp_path):
    from src.graph.graph import _default_initial_state, _edit_node

    article_dir = tmp_path / "article"
    article_dir.mkdir()
    raw = """# Article

> Source: [https://example.com](https://example.com)
> Platform: Web
> Captured: 2026-07-27
> Type: article

---

Written by Ada Lovelace.
"""
    (article_dir / "raw.md").write_text(raw, encoding="utf-8")
    (article_dir / "manifest.json").write_text(json.dumps({
        "article_id": "article",
        "article": {
            "url": "https://example.com",
            "platform": "web",
            "platform_label": "Web",
            "title": "Article",
            "author": None,
            "published_at": None,
            "captured_at": "2026-07-27",
            "content_type": "article",
        },
        "paths": {"raw": "raw.md", "reviewed": "reviewed.md", "assets": "assets"},
    }), encoding="utf-8")

    async def fake_edit(payload):
        return {
            "markdown": "# Reviewed\n\nBody.\n",
            "model": "review-model",
            "provider": "provider",
            "metadata_candidates": {
                "author": {"value": "Ada Lovelace", "evidence": "Written by Ada Lovelace"}
            },
        }

    monkeypatch.setattr("src.graph.graph.edit_article", SimpleNamespace(ainvoke=fake_edit))
    monkeypatch.setattr("src.graph.graph._write_success_report", lambda state: None)
    state = _default_initial_state()
    state.update({
        "article_id": "article",
        "platform": "web",
        "content_type": "article",
        "raw_markdown": raw,
        "reviewed_path": str(article_dir / "reviewed.md"),
        "assets_dir": "",
        "review_perspective": "original",
    })

    result = await _edit_node(state)

    assert result["metadata_enrichment_outcomes"][0]["action"] == "accepted"
    reviewed = (article_dir / "reviewed.md").read_text(encoding="utf-8")
    assert "> Author: Ada Lovelace" in reviewed
    manifest = json.loads((article_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["metadata_enrichment"]["fields"]["author"]["evidence"] == "Written by Ada Lovelace"


@pytest.mark.asyncio
async def test_review_uses_natural_custom_format_without_a_visible_summary(monkeypatch, tmp_path) -> None:
    from src.core.config.schema import Config, PipelineConfig, ReviewPerspectiveConfig
    from src.graph.tools import edit_article
    from src.integrations.ai_client import AIClient, AITextResponse

    format_file = tmp_path / "format.md"
    format_file.write_text("## Evidence\n\n(Keep the complete article. Do not display a summary.)", encoding="utf-8")
    config = Config.model_validate({
        "ai": {"provider": "test"},
        "ai_providers": {"test": {
            "model": "test-model", "api_base": "https://api.example.test/v1", "api_key": "test",
        }},
        "pipeline": PipelineConfig(perspectives={"research": ReviewPerspectiveConfig(
            label="Research", prompt_path="prompts/perspectives/original.en.md", template_path=str(format_file),
        )}, active_perspective="research"),
    })
    monkeypatch.setattr("src.graph.tools.load_config", lambda: config)

    async def generate_text(self, system_prompt: str, user_prompt: str):
        assert "Do not display a summary" in system_prompt
        assert "# Article format" in system_prompt
        assert "# Response protocol" in system_prompt
        assert '"slots"' not in system_prompt
        return AITextResponse(text=json.dumps({
            "title": "Reviewed", "markdown": "## Evidence\n\nAll original details.", "summary": "Internal context",
        }), model="test-model", provider="test")

    monkeypatch.setattr(AIClient, "generate_text", generate_text)
    result = await edit_article.ainvoke({
        "raw_markdown": "# Source\n\n> Source: [https://example.com](https://example.com)\n> Author: Ada\n\n---\n\nAll original details.",
        "feedback": "", "platform": "web", "content_type": "article", "perspective": "research",
    })
    assert "## Evidence\n\nAll original details." in result["markdown"]
    assert "> Author: Ada" in result["markdown"]
    assert "Internal context" not in result["markdown"]
    assert "AI Summary" not in result["markdown"]
