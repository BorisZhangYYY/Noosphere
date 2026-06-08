from __future__ import annotations

import shutil
from pathlib import Path

from src.core.models.manifest import write_article_manifest
from src.core.paths.output_paths import article_output_paths
from src.extractor_registry import extract_one
from src.integrations.assets import download_images


async def extract_to_output(url: str, output_dir: Path) -> Path:
    article = await extract_one(url)
    paths = article_output_paths(output_dir, article)
    paths.raw_path.parent.mkdir(parents=True, exist_ok=True)
    paths.reviewed_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate review Markdown and download images (pure function).
    markdown = article.to_review_markdown()
    updated_markdown, image_result = await download_images(markdown, paths.asset_dir)

    # Write the updated Markdown (with local image URLs) to raw.md, then copy to reviewed.md.
    paths.raw_path.write_text(updated_markdown, encoding="utf-8")
    shutil.copyfile(paths.raw_path, paths.reviewed_path)
    write_article_manifest(article, paths, image_result)
    return paths.reviewed_path
