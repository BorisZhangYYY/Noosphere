from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import os
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

import aiohttp


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
    asset_dir: Path
    downloaded: list[DownloadedImage] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    markdown_path: Path | None = None  # Optional; kept for backward compatibility.


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


def _looks_like_image_url(url: str) -> bool:
    """Return True if the URL is likely a real image resource.

    Filters out article-page URLs that are mis-identified as images by
    crawlers (e.g. WeChat 'follow' widget links).
    """
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.lower()

    # 1) Path ends with a known image extension
    if any(path.endswith(ext) for ext in {
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg",
    }):
        return True

    # 2) WeChat CDN query-string format (e.g. ?wx_fmt=jpeg)
    query = urllib.parse.parse_qs(parsed.query)
    if query.get("wx_fmt", [""])[0].lower() in {
        "jpeg", "jpg", "png", "gif", "webp", "bmp", "svg",
    }:
        return True

    # 3) Known image CDN hosts
    if parsed.hostname and parsed.hostname in {
        "mmbiz.qpic.cn", "mmbiz.qlogo.cn",
    }:
        return True

    return False


async def download_images(
    markdown: str, asset_dir: Path
) -> tuple[str, ImageDownloadResult]:
    """Download remote images referenced in *markdown* and return the updated Markdown.

    This is a pure function: it does not read or write files on disk. The caller
    is responsible for reading the original Markdown and writing the updated text.

    Args:
        markdown: The original Markdown body text.
        asset_dir: Directory where downloaded images should be saved.

    Returns:
        A tuple of (updated_markdown, download_result).
    """
    asset_dir.mkdir(parents=True, exist_ok=True)

    result = ImageDownloadResult(asset_dir=asset_dir)
    urls = []
    for match in MARKDOWN_IMAGE_RE.finditer(markdown):
        url, _ = split_image_target(match.group(2))
        if is_remote_url(url) and url not in urls and _looks_like_image_url(url):
            urls.append(url)

    semaphore = asyncio.Semaphore(5)
    tasks = [_download_one(url, asset_dir, index + 1, semaphore) for index, url in enumerate(urls)]
    download_results = await asyncio.gather(*tasks)

    replacements: dict[str, str] = {}
    for downloaded in download_results:
        if downloaded is None:
            continue
        rel_path = Path(os.path.relpath(downloaded.local_path, asset_dir.parent)).as_posix()
        replacements[downloaded.source_url] = rel_path
        result.downloaded.append(downloaded)

    if replacements:
        updated = MARKDOWN_IMAGE_RE.sub(lambda m: _replace_image_url(m, replacements), markdown)
    else:
        updated = markdown

    return updated, result


async def download_markdown_images(
    markdown_path: Path, assets_root: Path | None = None
) -> ImageDownloadResult:
    """Download remote images from a Markdown file and update the file in place.

    .. deprecated::
        Prefer ``download_images()`` for a pure function that does not mutate
        the file system. This wrapper is kept for backward compatibility.
    """
    markdown = markdown_path.read_text(encoding="utf-8")
    asset_dir = assets_root or markdown_path.parent / "assets" / safe_path_segment(markdown_path.stem)
    updated, result = await download_images(markdown, asset_dir)
    result.markdown_path = markdown_path
    markdown_path.write_text(updated, encoding="utf-8")
    return result


async def _download_one(
    url: str, asset_dir: Path, index: int, semaphore: asyncio.Semaphore
) -> DownloadedImage | None:
    async with semaphore:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
        extension = _extension_from_url(url)
        final_path = asset_dir / f"image_{index:02d}_{digest}{extension or '.bin'}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"User-Agent": DEFAULT_USER_AGENT},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    response.raise_for_status()
                    data = await response.read()
                    if not data:
                        raise ValueError("empty image response")
                    content_extension = _extension_from_content_type(response.headers.get("Content-Type"))

                    final_extension = extension or content_extension or ".bin"
                    final_path = asset_dir / f"image_{index:02d}_{digest}{final_extension}"
                    final_path.write_bytes(data)
        except (OSError, ValueError, aiohttp.ClientError):
            return None

        return DownloadedImage(source_url=url, local_path=final_path)


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
    """Return a mapping from Markdown image URL to resolved local file path.

    Only URLs without a scheme (e.g. ``assets/image.png``) are considered local.
    The URL is URL-decoded and resolved relative to *base_dir*; only files that
    actually exist on disk are returned.
    """
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
    """Rewrite image URLs in *markdown* using the *replacements* map.

    Keys are the original Markdown image URLs; values are the replacement URLs.
    References not present in the map are left unchanged.
    """
    return MARKDOWN_IMAGE_RE.sub(lambda m: _replace_image_url(m, replacements), markdown)
