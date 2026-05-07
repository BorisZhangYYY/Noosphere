from __future__ import annotations

from pathlib import Path

from src.core.config import load_config, siyuan_config
from src.core.markdown_upload import read_markdown_for_upload
from src.integrations.assets import local_image_paths, replace_image_urls
from src.integrations.siyuan import SiyuanClient


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
    local_images = local_image_paths(markdown, path.parent)
    if local_images:
        unique_paths = list(dict.fromkeys(local_images.values()))
        succ_map = client.upload_assets(unique_paths)
        replacements = {
            original_url: succ_map[local_path.name]
            for original_url, local_path in local_images.items()
            if local_path.name in succ_map
        }
        markdown = replace_image_urls(markdown, replacements)
    result = client.upload_markdown_under_parent(resolved_title, markdown, resolved_parent_id)
    return result.hpath
