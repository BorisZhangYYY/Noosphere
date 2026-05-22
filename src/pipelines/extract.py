from __future__ import annotations

import shutil
from pathlib import Path

from src.core.config.config import load_config
from src.core.models.manifest import write_article_manifest
from src.core.paths.output_paths import article_output_paths
from src.core.rules.platform_rules import write_noise_hints
from src.extractor_registry import extract_one
from src.integrations.assets import download_markdown_images


async def extract_to_output(url: str, output_dir: Path) -> Path:
    config = load_config()
    article = await extract_one(url, config)
    paths = article_output_paths(output_dir, article)
    paths.raw_path.parent.mkdir(parents=True, exist_ok=True)
    paths.reviewed_path.parent.mkdir(parents=True, exist_ok=True)
    paths.raw_path.write_text(article.to_review_markdown(), encoding="utf-8")
    image_result = download_markdown_images(paths.raw_path, assets_root=paths.asset_dir)
    if article.content_type == "article":
        write_noise_hints(paths.noise_hints_path, paths.raw_path.read_text(encoding="utf-8"), article.platform)
    shutil.copyfile(paths.raw_path, paths.reviewed_path)
    write_article_manifest(article, paths, image_result)
    return paths.reviewed_path
