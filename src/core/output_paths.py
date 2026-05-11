from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from src.core.article import Article


@dataclass(frozen=True)
class ArticleOutputPaths:
    raw_path: Path
    reviewed_path: Path
    asset_dir: Path
    manifest_path: Path


def article_output_id(article: Article) -> str:
    title_part = safe_filename(article.title, fallback=article.platform)
    digest = hashlib.sha1(article.url.encode("utf-8")).hexdigest()[:8]
    return f"{article.platform}_{title_part}_{digest}"


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
    return output_dir / article_output_id(article)


def article_output_paths(output_dir: Path, article: Article) -> ArticleOutputPaths:
    article_dir = article_output_path(output_dir, article)
    return ArticleOutputPaths(
        raw_path=article_dir / "raw.md",
        reviewed_path=article_dir / "reviewed.md",
        asset_dir=article_dir / "assets",
        manifest_path=article_dir / "manifest.json",
    )
