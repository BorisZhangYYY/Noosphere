from __future__ import annotations

from pathlib import Path

from src.common_func.assets import download_markdown_images, local_image_paths, replace_image_urls, split_image_target


class FakeResponse:
    headers = {"Content-Type": "image/png"}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return b"png-data"


def test_download_markdown_images_rewrites_remote_links(tmp_path, monkeypatch):
    markdown_path = tmp_path / "article.md"
    markdown_path.write_text("![alt](https://example.com/image)", encoding="utf-8")
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: FakeResponse())

    result = download_markdown_images(markdown_path)

    assert len(result.downloaded) == 1
    assert result.downloaded[0].local_path.exists()
    assert markdown_path.read_text(encoding="utf-8").startswith("![alt](assets/article/image_01_")
    assert "https://example.com/image" not in markdown_path.read_text(encoding="utf-8")


def test_local_image_paths_finds_existing_relative_images(tmp_path):
    image = tmp_path / "assets" / "image.png"
    image.parent.mkdir()
    image.write_bytes(b"data")
    markdown = "![alt](assets/image.png)\n![remote](https://example.com/image.png)"

    result = local_image_paths(markdown, tmp_path)

    assert result == {"assets/image.png": image.resolve()}


def test_local_image_paths_supports_spaces(tmp_path):
    image = tmp_path / "assets" / "article name" / "image 1.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"data")
    markdown = "![alt](assets/article name/image 1.png)"

    result = local_image_paths(markdown, tmp_path)

    assert result == {"assets/article name/image 1.png": image.resolve()}


def test_replace_image_urls_preserves_alt_text():
    markdown = "![alt](assets/image.png)"

    assert replace_image_urls(markdown, {"assets/image.png": "assets/uploaded.png"}) == "![alt](assets/uploaded.png)"


def test_split_image_target_keeps_optional_title():
    assert split_image_target('assets/image.png "caption"') == ("assets/image.png", '"caption"')
