from __future__ import annotations

from src.common_func.crawler import _markdown_text


class MarkdownResult:
    raw_markdown = "raw"
    fit_markdown = "fit"


def test_markdown_text_prefers_fit_markdown():
    assert _markdown_text(MarkdownResult()) == "fit"


def test_markdown_text_falls_back_to_raw_markdown():
    result = MarkdownResult()
    result.fit_markdown = ""

    assert _markdown_text(result) == "raw"
