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
    output_dir: Path,
    image_result: ImageDownloadResult,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "article_id": paths.raw_path.stem,
        "article": {
            "platform": article.platform,
            "platform_label": article.platform_label,
            "url": article.url,
            "title": article.title,
            "author": article.author,
            "published_at": article.published_at,
            "captured_at": article.captured_at,
            "status_code": article.status_code,
            "extra": article.extra,
        },
        "paths": {
            "raw": relative_to(paths.raw_path, output_dir),
            "reviewed": relative_to(paths.reviewed_path, output_dir),
            "assets": relative_to(paths.asset_dir, output_dir),
            "manifest": relative_to(paths.manifest_path, output_dir),
        },
        "assets": {
            "downloaded": [
                {
                    "source_url": image.source_url,
                    "local_path": relative_to(image.local_path, output_dir),
                }
                for image in image_result.downloaded
            ],
            "failed": image_result.failed,
        },
    }


def write_article_manifest(
    article: Article,
    paths: ArticleOutputPaths,
    output_dir: Path,
    image_result: ImageDownloadResult,
) -> Path:
    paths.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_article_manifest(article, paths, output_dir, image_result)
    paths.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return paths.manifest_path


def relative_to(path: Path, base_dir: Path) -> str:
    return Path(os.path.relpath(path, base_dir)).as_posix()
