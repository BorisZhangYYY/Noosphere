from __future__ import annotations

import sys
from pathlib import Path

from src.core.config.config import load_config, resolve_siyuan_token, siyuan_config
from src.core.markdown.upload_preparer import read_markdown_for_upload
from src.integrations.assets import local_image_paths, replace_image_urls
from src.integrations.siyuan import SiyuanClient


def upload_markdown_file(
    path: Path,
    title: str | None = None,
) -> str:
    """Upload a reviewed Markdown file to SiYuan under the configured parent document.

    Pipeline:
    1. Load SiYuan configuration and prepare the Markdown (strip leading H1, resolve title).
    2. Discover local image references relative to the Markdown file's directory.
    3. Upload the unique local images to SiYuan and replace their URLs in the Markdown body.
    4. Upload the final Markdown document under the configured parent.

    Images that fail to upload keep their original local URLs; only successfully uploaded
    assets are rewritten so the SiYuan document can render them.
    """
    config = load_config()
    sconfig = siyuan_config(config)
    resolved_parent_id = sconfig.get("default_parent_id") or None
    if not resolved_parent_id:
        raise ValueError("siyuan.default_parent_id is required for upload")

    resolved_api_base = sconfig.get("api_base", "http://127.0.0.1:6806")
    token = resolve_siyuan_token(config)

    # Step 1: Prepare Markdown content and document title.
    resolved_title, markdown = read_markdown_for_upload(path, title)
    client = SiyuanClient(api_base=resolved_api_base, token=token)

    # Step 2: Find local images referenced from the Markdown file's directory.
    local_images = local_image_paths(markdown, path.parent)
    if local_images:
        # Step 3: Upload unique local images and rewrite Markdown URLs for successful uploads.
        unique_paths = list(dict.fromkeys(local_images.values()))
        succ_map = client.upload_assets(unique_paths)

        replacements: dict[str, str] = {}
        missing: list[str] = []
        for original_url, local_path in local_images.items():
            # Prefer an exact filename match; fall back to a basename match in case
            # the server returns keys with directory prefixes.
            uploaded_url = succ_map.get(local_path.name) or next(
                (
                    url
                    for key, url in succ_map.items()
                    if Path(key).name == local_path.name
                ),
                "",
            )
            if uploaded_url:
                replacements[original_url] = uploaded_url
            else:
                missing.append(local_path.name)

        if missing:
            sys.stderr.write(
                f"[upload] Warning: the following images were not uploaded by SiYuan: {missing}\n"
            )

        if replacements:
            markdown = replace_image_urls(markdown, replacements)

    # Step 4: Upload the Markdown document under the configured parent.
    result = client.upload_markdown_under_parent(resolved_title, markdown, resolved_parent_id)
    return result.hpath
