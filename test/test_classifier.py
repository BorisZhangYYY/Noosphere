from __future__ import annotations

from pathlib import Path

import pytest

from src.classifier import (
    article_output_path,
    classify_url,
    markdown_without_leading_h1,
    parse_args,
    read_markdown_for_upload,
    safe_filename,
    title_from_markdown,
    write_article_output,
)
from src.common_func.siyuan import SiyuanClient


class TestSafeFilename:
    def test_strips_special_chars(self):
        result = safe_filename("file/name:with*special?chars")

        assert "/" not in result
        assert ":" not in result
        assert "*" not in result
        assert "?" not in result

    def test_strips_whitespace(self):
        result = safe_filename("  hello   world  ")

        assert result == "hello world"

    def test_fallback_for_empty(self):
        assert safe_filename("") == "item"

    def test_truncates_long_names(self):
        assert len(safe_filename("a" * 100, max_len=50)) <= 50


class TestClassifyUrl:
    def test_uses_known_platform_patterns(self):
        assert classify_url("https://zhuanlan.zhihu.com/p/123", {}) == "zhihu_zhuanlan"
        assert classify_url("https://mp.weixin.qq.com/s/abc", {}) == "wechat_mp"

    def test_ignores_siyuan_config(self):
        config = {
            "siyuan": {"url_patterns": ["example.com"]},
            "zhihu_zhuanlan": {"url_patterns": ["custom.example/article"]},
        }

        assert classify_url("https://custom.example/article/1", config) == "zhihu_zhuanlan"

    def test_rejects_unsupported_url(self):
        with pytest.raises(ValueError, match="Unsupported URL"):
            classify_url("https://example.com/article", {})


class TestArticleOutput:
    def test_output_path_is_single_article_filename(self, sample_article):
        path = article_output_path(Path("outputs"), sample_article)

        assert path.name.startswith("zhihu_zhuanlan_Test Article Title_")
        assert path.suffix == ".md"

    def test_write_article_output_uses_review_markdown(self, tmp_path, sample_article):
        path = write_article_output(tmp_path, sample_article)

        text = path.read_text(encoding="utf-8")
        assert text.startswith("# Test Article Title\n")
        assert "> 来源：" in text
        assert "---" in text
        assert "This is test content." in text


class TestMarkdownUploadParsing:
    def test_title_from_first_h1(self):
        markdown = "\n# Reviewed Title\n\n## AI 总结\n"

        assert title_from_markdown(markdown, "fallback") == "Reviewed Title"

    def test_title_falls_back_when_no_h1(self):
        assert title_from_markdown("## AI 总结\n", "fallback") == "fallback"

    def test_strips_only_leading_h1(self):
        markdown = "# Title\n\n## AI 总结\n\n---\n\n# Inner Heading\n"

        result = markdown_without_leading_h1(markdown)

        assert result.startswith("## AI 总结")
        assert "# Inner Heading" in result

    def test_read_upload_markdown_preserves_markdown_table(self, tmp_path):
        path = tmp_path / "reviewed.md"
        path.write_text("# Reviewed\n\n| A | B |\n| - | - |\n| 1 | 2 |\n", encoding="utf-8")

        title, markdown = read_markdown_for_upload(path)

        assert title == "Reviewed"
        assert markdown.startswith("| A | B |")
        assert "data-type=\"table\"" not in markdown

    def test_title_override_still_removes_file_h1(self, tmp_path):
        path = tmp_path / "reviewed.md"
        path.write_text("# Old Title\n\nBody\n", encoding="utf-8")

        title, markdown = read_markdown_for_upload(path, title="New Title")

        assert title == "New Title"
        assert markdown == "Body\n"


class TestCliArgs:
    def test_extract_requires_single_url(self):
        args = parse_args(["extract", "https://zhuanlan.zhihu.com/p/123"])

        assert args.command == "extract"
        assert args.url == "https://zhuanlan.zhihu.com/p/123"

    def test_extract_rejects_multiple_urls(self):
        with pytest.raises(SystemExit):
            parse_args(["extract", "https://one.example", "https://two.example"])

    def test_upload_accepts_single_file(self):
        args = parse_args(["upload", "outputs/reviewed.md", "--title", "Reviewed"])

        assert args.command == "upload"
        assert args.file == Path("outputs/reviewed.md")
        assert args.title == "Reviewed"


class FakeSiyuanClient(SiyuanClient):
    def __init__(self, existing_id: str | None = None):
        self.existing_id = existing_id
        self.created_payload = None
        self.updated_payload = None

    def parent_location(self, parent_doc_id: str) -> tuple[str, str]:
        return "notebook-id", "/Parent"

    def ids_by_hpath(self, notebook_id: str, hpath: str) -> list[str]:
        return [self.existing_id] if self.existing_id else []

    def create_doc_with_md(self, notebook_id: str, hpath: str, markdown: str) -> str:
        self.created_payload = {
            "notebook_id": notebook_id,
            "hpath": hpath,
            "markdown": markdown,
        }
        return "created-doc-id"

    def update_block_markdown(self, block_id: str, markdown: str) -> None:
        self.updated_payload = {
            "block_id": block_id,
            "markdown": markdown,
        }


class TestSiyuanMarkdownUpload:
    def test_creates_doc_with_markdown_table_not_dom(self):
        client = FakeSiyuanClient()
        markdown = "| A | B |\n| - | - |\n| 1 | 2 |\n"

        result = client.upload_markdown_under_parent("Reviewed", markdown, "parent-id")

        assert result.created is True
        assert result.hpath == "/Parent/Reviewed"
        assert client.created_payload["markdown"] == markdown
        assert "data-type=\"table\"" not in client.created_payload["markdown"]

    def test_updates_existing_doc_with_markdown(self):
        client = FakeSiyuanClient(existing_id="existing-doc-id")

        result = client.upload_markdown_under_parent("Reviewed", "Body\n", "parent-id")

        assert result.created is False
        assert client.updated_payload == {"block_id": "existing-doc-id", "markdown": "Body\n"}
