from __future__ import annotations

import hashlib
import mimetypes
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]*)\)")
IMAGE_TARGET_RE = re.compile(r"^(.+?)\s+([\"'][^\"']*[\"'])$")
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class DownloadedImage:
    source_url: str
    local_path: Path


@dataclass
class ImageDownloadResult:
    markdown_path: Path
    asset_dir: Path
    downloaded: list[DownloadedImage] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def is_remote_url(url: str) -> bool:
    return urllib.parse.urlparse(url).scheme in {"http", "https"}


def is_local_image_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme == "" and bool(parsed.path)


def safe_path_segment(text: str, fallback: str = "assets", max_len: int = 80) -> str:
    cleaned = text.strip()
    for char in ["/", "\\", ":", "*", "?", "\"", "<", ">", "|"]:
        cleaned = cleaned.replace(char, "-")
    cleaned = " ".join(cleaned.split()).strip(" .-_")
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip(" .-_")
    return cleaned or fallback


def _extension_from_url(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    suffix = Path(path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}:
        return suffix
    return ""


def _extension_from_content_type(content_type: str | None) -> str:
    if not content_type:
        return ""
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type == "image/jpeg":
        return ".jpg"
    return mimetypes.guess_extension(media_type) or ""


def download_markdown_images(markdown_path: Path, assets_root: Path | None = None) -> ImageDownloadResult:
    markdown = markdown_path.read_text(encoding="utf-8")
    asset_dir = assets_root or markdown_path.parent / "assets" / safe_path_segment(markdown_path.stem)
    asset_dir.mkdir(parents=True, exist_ok=True)

    result = ImageDownloadResult(markdown_path=markdown_path, asset_dir=asset_dir)
    replacements: dict[str, str] = {}
    urls = []
    for match in MARKDOWN_IMAGE_RE.finditer(markdown):
        url, _ = split_image_target(match.group(2))
        if is_remote_url(url) and url not in urls:
            urls.append(url)

    for index, url in enumerate(urls, 1):
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
        extension = _extension_from_url(url)
        temp_path = asset_dir / f"image_{index:02d}_{digest}{extension or '.bin'}"
        try:
            request = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read()
                if not data:
                    raise ValueError("empty image response")
                content_extension = _extension_from_content_type(response.headers.get("Content-Type"))
                final_extension = extension or content_extension or ".bin"
                final_path = asset_dir / f"image_{index:02d}_{digest}{final_extension}"
                final_path.write_bytes(data)
        except (OSError, ValueError, urllib.error.URLError) as exc:
            result.failed[url] = str(exc)
            continue

        rel_path = final_path.relative_to(markdown_path.parent).as_posix()
        replacements[url] = rel_path
        result.downloaded.append(DownloadedImage(source_url=url, local_path=final_path))

        if temp_path.exists() and temp_path != final_path:
            temp_path.unlink()

    if replacements:
        updated = MARKDOWN_IMAGE_RE.sub(lambda m: _replace_image_url(m, replacements), markdown)
        markdown_path.write_text(updated, encoding="utf-8")

    return result


def _replace_image_url(match: re.Match[str], replacements: dict[str, str]) -> str:
    alt = match.group(1)
    url, title = split_image_target(match.group(2))
    replacement = replacements.get(url)
    if not replacement:
        return match.group(0)
    suffix = f" {title}" if title else ""
    return f"![{alt}]({replacement}{suffix})"


def split_image_target(target: str) -> tuple[str, str | None]:
    stripped = target.strip()
    match = IMAGE_TARGET_RE.match(stripped)
    if match:
        return match.group(1).strip(), match.group(2)
    return stripped, None


def local_image_paths(markdown: str, base_dir: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for match in MARKDOWN_IMAGE_RE.finditer(markdown):
        url, _ = split_image_target(match.group(2))
        if not is_local_image_url(url):
            continue
        path = (base_dir / urllib.parse.unquote(url)).resolve()
        if path.exists() and path.is_file():
            paths[url] = path
    return paths


def replace_image_urls(markdown: str, replacements: dict[str, str]) -> str:
    return MARKDOWN_IMAGE_RE.sub(lambda m: _replace_image_url(m, replacements), markdown)
