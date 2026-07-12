"""Tests for the LangGraph-based article pipeline."""
from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from src.graph.graph import (
    _default_initial_state,
    build_ai_review_graph,
    build_extract_graph,
    build_pipeline_graph,
    build_upload_graph,
)


@pytest.fixture
def initial_state():
    return _default_initial_state()


def test_default_initial_state_has_required_keys(initial_state):
    required_keys = {
        "article_id",
        "url",
        "platform",
        "content_type",
        "title",
        "output_dir",
        "reviewed_path",
        "assets_dir",
        "raw_markdown",
        "assets",
        "download_failed",
        "reviewed_markdown",
        "image_filter_result",
        "validation_result",
        "feedback",
        "attempts",
        "max_attempts",
        "human_approved",
        "review_model",
        "review_provider",
        "upload_target",
        "upload_result",
        "error",
        "status",
    }
    assert set(initial_state.keys()) == required_keys


@pytest.mark.parametrize(
    "builder",
    [
        build_extract_graph,
        build_ai_review_graph,
        build_upload_graph,
        build_pipeline_graph,
    ],
)
def test_graph_compiles(builder):
    graph = builder().compile(checkpointer=MemorySaver())
    assert graph is not None


def test_get_checkpointer_sqlite(monkeypatch, tmp_path):
    from src.core.config.config import load_config
    from src.graph.graph import _get_checkpointer

    config = load_config()
    monkeypatch.setattr(config.checkpoint, "backend", "sqlite")
    monkeypatch.setattr(config.checkpoint, "sqlite_path", str(tmp_path / "test.sqlite"))

    saver = _get_checkpointer()
    assert isinstance(saver, SqliteSaver)


def test_get_checkpointer_memory(monkeypatch):
    from src.core.config.config import load_config
    from src.graph.graph import _get_checkpointer

    config = load_config()
    monkeypatch.setattr(config.checkpoint, "backend", "memory")

    saver = _get_checkpointer()
    assert isinstance(saver, MemorySaver)
