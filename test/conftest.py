"""Shared fixtures for classifier tests."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from src.common_func.article import Article


@pytest.fixture
def temp_output_dir(tmp_path):
    """Provide a clean temporary output directory."""
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    yield output_dir
    shutil.rmtree(output_dir, ignore_errors=True)


@pytest.fixture
def sample_article():
    return Article(
        platform="zhihu_zhuanlan",
        platform_label="知乎专栏",
        url="https://zhuanlan.zhihu.com/p/2014808999774691482",
        title="Test Article Title",
        markdown="# Test Article Title\n\nThis is test content.",
        author="Test Author",
        published_at="2026-01-01T00:00:00.000Z",
        captured_at="2026-01-01T12:00:00+08:00",
        status_code=200,
        extra={"crawl_success": True, "crawl_error": ""},
    )
