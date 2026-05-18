from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from src.core.article import Article
from src.core.output_paths import ArticleOutputPaths
from src.integrations.assets import ImageDownloadResult


SCHEMA_VERSION = 1


def build_article_manifest(
    article: Article,
    paths: ArticleOutputPaths,
    image_result: ImageDownloadResult,
) -> dict[str, Any]:
    article_dir = paths.manifest_path.parent
    return {
        "schema_version": SCHEMA_VERSION,
        "article_id": paths.manifest_path.parent.name,
        "article": {
            "platform": article.platform,
            "platform_label": article.platform_label,
            "url": article.url,
            "title": article.title,
            "author": article.author,
            "published_at": article.published_at,
            "captured_at": article.captured_at,
            "status_code": article.status_code,
            "content_type": article.content_type,
            "extra": article.extra,
        },
        "paths": {
            "raw": relative_to(paths.raw_path, article_dir),
            "reviewed": relative_to(paths.reviewed_path, article_dir),
            "assets": relative_to(paths.asset_dir, article_dir),
            "noise_hints": relative_to(paths.noise_hints_path, article_dir),
            "manifest": relative_to(paths.manifest_path, article_dir),
        },
        "assets": {
            "downloaded": [
                {
                    "source_url": image.source_url,
                    "local_path": relative_to(image.local_path, article_dir),
                }
                for image in image_result.downloaded
            ],
            "failed": image_result.failed,
        },
    }


def write_article_manifest(
    article: Article,
    paths: ArticleOutputPaths,
    image_result: ImageDownloadResult,
) -> Path:
    paths.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_article_manifest(article, paths, image_result)
    paths.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return paths.manifest_path


def relative_to(path: Path, base_dir: Path) -> str:
    return Path(os.path.relpath(path, base_dir)).as_posix()


def resolve_manifest_path_entry(manifest_path: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return manifest_path.parent / path
