from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.cli import parse_args
from src.core.markdown_upload import (
    markdown_without_leading_h1,
    read_markdown_for_upload,
    title_from_markdown,
)
from src.core.output_paths import (
    article_output_path,
    article_output_paths,
    safe_filename,
)
from src.extractor_registry import classify_url
from src.integrations.siyuan import SiyuanClient
from src.pipelines.extract import extract_to_output
from src.pipelines.upload import upload_markdown_file


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

    def test_article_output_paths_are_layered(self, sample_article):
        paths = article_output_paths(Path("outputs"), sample_article)

        assert paths.raw_path.parent == Path("outputs/raw")
        assert paths.reviewed_path.parent == Path("outputs/reviewed")
        assert paths.asset_dir.parent == Path("outputs/assets")
        assert paths.manifest_path.parent == Path("outputs/manifests")

    def test_extract_to_output_writes_raw_and_reviewed(self, tmp_path, sample_article, monkeypatch):
        async def fake_extract_one(url: str, config: dict | None = None):
            return sample_article

        monkeypatch.setattr("src.pipelines.extract.extract_one", fake_extract_one)

        reviewed_path = asyncio.run(extract_to_output("https://zhuanlan.zhihu.com/p/123", tmp_path))
        raw_path = tmp_path / "raw" / reviewed_path.name

        assert reviewed_path.parent == tmp_path / "reviewed"
        assert raw_path.exists()
        assert reviewed_path.exists()
        assert raw_path.read_text(encoding="utf-8") == reviewed_path.read_text(encoding="utf-8")

    def test_extract_to_output_writes_manifest(self, tmp_path, sample_article, monkeypatch):
        async def fake_extract_one(url: str, config: dict | None = None):
            return sample_article

        monkeypatch.setattr("src.pipelines.extract.extract_one", fake_extract_one)

        reviewed_path = asyncio.run(extract_to_output("https://zhuanlan.zhihu.com/p/123", tmp_path))
        manifest_path = tmp_path / "manifests" / f"{reviewed_path.stem}.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        assert manifest["schema_version"] == 1
        assert manifest["article_id"] == reviewed_path.stem
        assert manifest["article"]["url"] == sample_article.url
        assert manifest["article"]["platform"] == "zhihu_zhuanlan"
        assert manifest["paths"]["raw"] == f"raw/{reviewed_path.name}"
        assert manifest["paths"]["reviewed"] == f"reviewed/{reviewed_path.name}"
        assert manifest["paths"]["manifest"] == f"manifests/{reviewed_path.stem}.json"
        assert manifest["assets"] == {"downloaded": [], "failed": {}}


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
        args = parse_args(["upload", "outputs/reviewed.md"])

        assert args.command == "upload"
        assert args.file == Path("outputs/reviewed.md")

    def test_manual_review_accepts_reviewed_file(self):
        args = parse_args(["manual-review", "outputs/reviewed/article.md", "--overwrite"])

        assert args.command == "manual-review"
        assert args.file == Path("outputs/reviewed/article.md")
        assert args.overwrite is True

    def test_validate_accepts_reviewed_file(self):
        args = parse_args(["validate", "outputs/reviewed/article.md"])

        assert args.command == "validate"
        assert args.file == Path("outputs/reviewed/article.md")

    def test_ai_review_accepts_reviewed_file(self):
        args = parse_args(["ai-review", "outputs/reviewed/article.md"])

        assert args.command == "ai-review"
        assert args.file == Path("outputs/reviewed/article.md")

    def test_verify_accepts_reviewed_file(self):
        args = parse_args(["verify", "outputs/reviewed/article.md"])

        assert args.command == "verify"
        assert args.file == Path("outputs/reviewed/article.md")

    def test_run_accepts_url(self):
        args = parse_args(["run", "https://mp.weixin.qq.com/s/abc"])

        assert args.command == "run"
        assert args.url == "https://mp.weixin.qq.com/s/abc"

    def test_cli_module_entrypoint_shows_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "src.cli", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        assert "extract" in result.stdout
        assert "upload" in result.stdout
        assert "manual-review" in result.stdout
        assert "validate" in result.stdout
        assert "ai-review" in result.stdout
        assert "verify" in result.stdout


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


class UploadingFakeSiyuanClient:
    last_instance = None

    def __init__(self, api_base: str, token: str):
        self.api_base = api_base
        self.token = token
        self.parent_id = None
        self.uploaded_assets = []
        self.uploaded_markdown = None
        UploadingFakeSiyuanClient.last_instance = self

    def upload_assets(self, files: list[Path]):
        self.uploaded_assets = files
        return {path.name: f"assets/{path.stem}-uploaded{path.suffix}" for path in files}

    def upload_markdown_under_parent(self, title: str, markdown: str, parent_id: str):
        self.parent_id = parent_id
        self.uploaded_markdown = markdown
        return type("Result", (), {"hpath": f"/{title}"})()


def test_upload_markdown_file_uploads_local_assets(tmp_path, monkeypatch):
    image = tmp_path / "assets" / "image.png"
    image.parent.mkdir()
    image.write_bytes(b"data")
    reviewed_dir = tmp_path / "reviewed"
    reviewed_dir.mkdir()
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    reviews_dir = tmp_path / "reviews"
    reviews_dir.mkdir()
    markdown = reviewed_dir / "reviewed.md"
    markdown.write_text(
        "# Reviewed\n\n## AI Summary\n\n- Summary\n\n---\n\n## Main Article\n\n![alt](../assets/image.png)\n",
        encoding="utf-8",
    )
    (manifest_dir / "reviewed.json").write_text('{"article_id": "reviewed", "article": {}}', encoding="utf-8")
    (reviews_dir / "reviewed.json").write_text(
        '{"article_id": "reviewed", "status": "reviewed", "review": {"summary": "Reviewed."}}',
        encoding="utf-8",
    )
    monkeypatch.setattr("src.pipelines.upload.SiyuanClient", UploadingFakeSiyuanClient)
    monkeypatch.setattr(
        "src.pipelines.upload.load_config",
        lambda: {
            "siyuan": {
                "api_base": "http://siyuan",
                "default_parent_id": "parent-id",
                "token": "test-token",
            }
        },
    )

    hpath = upload_markdown_file(markdown)

    client = UploadingFakeSiyuanClient.last_instance
    assert hpath == "/Reviewed"
    assert client.api_base == "http://siyuan"
    assert client.token == "test-token"
    assert client.parent_id == "parent-id"
    assert client.uploaded_assets == [image.resolve()]
    assert "## AI Summary" in client.uploaded_markdown
    assert "![alt](assets/image-uploaded.png)" in client.uploaded_markdown


def test_upload_markdown_file_rejects_unreviewed_markdown(tmp_path):
    reviewed_dir = tmp_path / "reviewed"
    reviewed_dir.mkdir()
    markdown = reviewed_dir / "reviewed.md"
    markdown.write_text("# Reviewed\n\nBody\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Reviewed Markdown failed validation"):
        upload_markdown_file(markdown)
