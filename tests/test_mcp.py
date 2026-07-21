"""Boundary validation tests for the MCP service."""
from __future__ import annotations

import pytest

from src.mcp.server import _validate_article_id, _validate_upload_target


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
