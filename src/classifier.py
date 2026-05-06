from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Awaitable, Callable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common_func.article import Article
from src.common_func.siyuan import SiyuanClient
from src.wechat_mp import extractor as wechat_mp
from src.zhihu_zhuanlan import extractor as zhihu_zhuanlan


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "config.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs"

Extractor = Callable[[str], Awaitable[Article]]

EXTRACTORS: dict[str, tuple[Callable[[str], bool], Extractor]] = {
    "wechat_mp": (wechat_mp.handles, wechat_mp.extract),
    "zhihu_zhuanlan": (zhihu_zhuanlan.handles, zhihu_zhuanlan.extract),
}

H1_RE = re.compile(r"^#\s+(.+?)\s*$")


def load_config(path: Path = DEFAULT_CONFIG) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def siyuan_config(config: dict) -> dict:
    value = config.get("siyuan", {})
    return value if isinstance(value, dict) else {}


def safe_filename(text: str, fallback: str = "item", max_len: int = 80) -> str:
    cleaned = text.strip()
    for char in ["/", "\\", ":", "*", "?", "\"", "<", ">", "|"]:
        cleaned = cleaned.replace(char, "-")
    cleaned = " ".join(cleaned.split())
    cleaned = cleaned.strip(" .-_")
    if not cleaned:
        cleaned = fallback
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip(" .-_")
    return cleaned or fallback


def article_output_path(output_dir: Path, article: Article) -> Path:
    title_part = safe_filename(article.title, fallback=article.platform)
    digest = hashlib.sha1(article.url.encode("utf-8")).hexdigest()[:8]
    filename = f"{article.platform}_{title_part}_{digest}.md"
    return output_dir / filename


def write_article_output(output_dir: Path, article: Article) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = article_output_path(output_dir, article)
    path.write_text(article.to_review_markdown(), encoding="utf-8")
    return path


def classify_url(url: str, config: dict | None = None) -> str:
    config = config or load_config()
    for platform, value in config.items():
        if platform == "siyuan" or not isinstance(value, dict):
            continue
        for pattern in value.get("url_patterns", []):
            if pattern in url:
                if platform not in EXTRACTORS:
                    raise ValueError(f"Configured platform has no extractor: {platform}")
                return platform

    for platform, (handles, _) in EXTRACTORS.items():
        if handles(url):
            return platform
    raise ValueError(f"Unsupported URL: {url}")


async def extract_one(url: str, config: dict | None = None) -> Article:
    platform = classify_url(url, config)
    _, extractor = EXTRACTORS[platform]
    return await extractor(url)


async def extract_to_output(url: str, output_dir: Path) -> Path:
    config = load_config()
    article = await extract_one(url, config)
    return write_article_output(output_dir, article)


def title_from_markdown(markdown: str, fallback: str) -> str:
    for line in markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        match = H1_RE.match(line.strip())
        if match:
            title = match.group(1).strip()
            if title:
                return title
    return fallback


def markdown_without_leading_h1(markdown: str) -> str:
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    while lines and not lines[0].strip():
        lines.pop(0)

    if lines:
        match = H1_RE.match(lines[0].strip())
        if match:
            lines.pop(0)
            while lines and not lines[0].strip():
                lines.pop(0)

    return "\n".join(lines).strip() + "\n"


def read_markdown_for_upload(path: Path, title: str | None = None) -> tuple[str, str]:
    markdown = path.read_text(encoding="utf-8")
    fallback = safe_filename(path.stem, fallback="未命名文章")
    resolved_title = title or title_from_markdown(markdown, fallback)
    return resolved_title, markdown_without_leading_h1(markdown)


def upload_markdown_file(
    path: Path,
    parent_id: str | None,
    api_base: str,
    title: str | None = None,
) -> str:
    config = load_config()
    sconfig = siyuan_config(config)
    resolved_parent_id = parent_id or sconfig.get("default_parent_id") or None
    if not resolved_parent_id:
        raise ValueError("--parent-id or siyuan.default_parent_id is required for upload")

    resolved_api_base = api_base or sconfig.get("api_base", "http://127.0.0.1:6806")
    token_env = sconfig.get("token_env", "SIYUAN_TOKEN")
    resolved_title, markdown = read_markdown_for_upload(path, title)
    client = SiyuanClient(api_base=resolved_api_base, token_env=token_env)
    result = client.upload_markdown_under_parent(resolved_title, markdown, resolved_parent_id)
    return result.hpath


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract one supported article into Markdown, then upload a reviewed Markdown file to SiYuan."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract", help="Extract one article URL into outputs/.")
    extract_parser.add_argument("url", help="Article URL to extract.")
    extract_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for extracted Markdown.")

    upload_parser = subparsers.add_parser("upload", help="Upload one reviewed Markdown file to SiYuan.")
    upload_parser.add_argument("file", type=Path, help="Reviewed Markdown file to upload.")
    upload_parser.add_argument("--parent-id", help="SiYuan target notebook ID or parent document block ID.")
    upload_parser.add_argument("--api-base", default="", help="SiYuan API base URL.")
    upload_parser.add_argument("--title", help="Override the document title inferred from the first H1 or filename.")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        if args.command == "extract":
            path = asyncio.run(extract_to_output(args.url, args.output_dir))
            print(f"Extracted: {path}")
            print("Next: review and edit this Markdown file, then run `python src/classifier.py upload FILE`.")
            return 0

        if args.command == "upload":
            if not args.file.exists():
                print(f"Error: Markdown file not found: {args.file}")
                return 1
            hpath = upload_markdown_file(args.file, args.parent_id, args.api_base, args.title)
            print(f"Uploaded: {hpath}")
            return 0

    except Exception as exc:  # noqa: BLE001 - CLI should show a concise error.
        print(f"Error: {exc}")
        return 1

    print(f"Error: unsupported command: {args.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
