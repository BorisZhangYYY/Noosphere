from __future__ import annotations

from src.core.markdown_links import bare_markdown_urls, normalize_markdown_links


def test_normalizes_source_url_metadata_line():
    markdown = "> 来源：https://mp.weixin.qq.com/s/test\n"

    assert normalize_markdown_links(markdown) == "> 来源：[https://mp.weixin.qq.com/s/test](https://mp.weixin.qq.com/s/test)\n"


def test_normalizes_related_link_list_item():
    markdown = "- VS Code 1.119 更新日志：https://code.visualstudio.com/updates/v1_119\n"

    assert normalize_markdown_links(markdown) == "- [VS Code 1.119 更新日志](https://code.visualstudio.com/updates/v1_119)\n"


def test_preserves_existing_markdown_links():
    markdown = "[VS Code](https://code.visualstudio.com/updates/v1_119)\n"

    assert normalize_markdown_links(markdown) == markdown


def test_does_not_normalize_code_urls():
    markdown = "`https://example.com`\n\n```text\nhttps://example.com\n```\n"

    assert normalize_markdown_links(markdown) == markdown


def test_finds_only_unprotected_bare_urls():
    markdown = (
        "https://bare.example/path\n"
        "[linked](https://linked.example/path)\n"
        "`https://code.example/path`\n"
        "```text\n"
        "https://fenced.example/path\n"
        "```\n"
    )

    assert bare_markdown_urls(markdown) == ["https://bare.example/path"]
