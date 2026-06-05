"""SiYuan upload adapter.

Encapsulates the full SiYuan upload pipeline inside the UploadAdapter contract.
Images are uploaded to SiYuan's asset system and their URLs are rewritten in the
Markdown body before the document is created or updated.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from src.core.config.schema import SiyuanConfig
from src.core.markdown.upload_preparer import read_markdown_for_upload
from src.core.upload.adapter import UploadAdapter
from src.integrations.assets import local_image_paths, replace_image_urls
from src.integrations.siyuan import SiyuanClient

if TYPE_CHECKING:
    pass


class SiyuanAdapter(UploadAdapter):
    """Upload reviewed Markdown to SiYuan."""

    def __init__(self, config: SiyuanConfig) -> None:
        if not config.default_parent_id:
            raise ValueError("siyuan.default_parent_id is required for upload")
        if not config.token:
            raise ValueError("siyuan.token is required for upload")
        self._parent_id = config.default_parent_id
        self._client = SiyuanClient(api_base=config.api_base, token=config.token)

    @property
    def platform_name(self) -> str:
        return "SiYuan"

    async def upload(self, path: Path, title: str | None = None) -> str:
        """Upload Markdown to SiYuan.

        Pipeline:
        1. Prepare Markdown (strip H1, resolve title).
        2. Discover local images relative to the Markdown file.
        3. Upload images to SiYuan and replace URLs in the Markdown.
        4. Create or update the SiYuan document under the configured parent.
        """
        resolved_title, markdown = read_markdown_for_upload(path, title)

        # Handle local images
        local_images = local_image_paths(markdown, path.parent)
        if local_images:
            markdown = await self._upload_and_replace_images(markdown, local_images)

        # Upload the Markdown document
        result = await asyncio.to_thread(
            self._client.upload_markdown_under_parent,
            resolved_title,
            markdown,
            self._parent_id,
        )
        return result.hpath

    async def _upload_and_replace_images(
        self,
        markdown: str,
        local_images: dict[str, Path],
    ) -> str:
        """Upload unique local images to SiYuan and rewrite Markdown URLs."""
        unique_paths = list(dict.fromkeys(local_images.values()))
        succ_map = await asyncio.to_thread(self._client.upload_assets, unique_paths)

        replacements: dict[str, str] = {}
        missing: list[str] = []
        for original_url, local_path in local_images.items():
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

        return markdown
