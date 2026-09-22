"""Shared transformations for article image references."""
from __future__ import annotations
import re
import urllib.parse
from pathlib import Path
from src.integrations.assets import MARKDOWN_IMAGE_RE, split_image_target

def _markdown_image_name(target: str) -> str:
    url, _ = split_image_target(target)
    path = urllib.parse.urlsplit(url).path
    return Path(urllib.parse.unquote(path)).name


def _replace_image_target(markdown: str, asset_name: str, target: str | None) -> str:
    def replace(match: "re.Match[str]") -> str:
        if _markdown_image_name(match.group(2)) != asset_name:
            return match.group(0)
        if target is None:
            return ""
        return f"![{match.group(1)}]({target})"

    return MARKDOWN_IMAGE_RE.sub(replace, markdown)


def _ensure_inventory_images_visible(
    markdown: str,
    raw_markdown: str,
    *,
    article_id: str,
    active_names: set[str],
    removed_names: set[str],
) -> str:
    """Project every local image into the editor without mutating reviewed.md."""
    from src.core.review.image_filter import _restore_images_to_original_positions
    from src.core.review.output_contract import normalize_source_metadata_boundary

    inventory = active_names | removed_names
    visible = normalize_source_metadata_boundary(markdown, raw_markdown)
    present = {_markdown_image_name(match.group(2)) for match in MARKDOWN_IMAGE_RE.finditer(visible)}
    missing_paths = {
        f"assets/{name}"
        for name in inventory - present
    }
    visible = _restore_images_to_original_positions(visible, raw_markdown, missing_paths)
    present = {_markdown_image_name(match.group(2)) for match in MARKDOWN_IMAGE_RE.finditer(visible)}
    for name in sorted(inventory - present):
        alt = Path(name).stem.replace("_", " ").replace("-", " ")
        visible = visible.rstrip() + f"\n\n![{alt}](assets/{name})\n"

    for name in removed_names:
        encoded_article = urllib.parse.quote(article_id, safe="")
        encoded_name = urllib.parse.quote(name, safe="")
        removed_target = f"/api/v1/articles/{encoded_article}/removed/{encoded_name}?state=removed"
        visible = _replace_image_target(visible, name, removed_target)
    return visible


def _persistable_reviewed_markdown(markdown: str, removed_names: set[str]) -> str:
    """Remove editor-only references to assets that remain in removed/."""
    from src.core.article_metadata import strip_editor_artifacts

    markdown = strip_editor_artifacts(markdown)
    for name in removed_names:
        markdown = _replace_image_target(markdown, name, None)
    return markdown.rstrip() + "\n"

