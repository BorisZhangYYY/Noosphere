"""Shared transformations for article image references."""
from __future__ import annotations
import hashlib
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
    removed_positions: dict | None = None,
) -> str:
    """Project every local image into the editor without mutating reviewed.md."""
    from src.core.review.image_filter import _restore_images_to_original_positions
    from src.core.review.output_contract import normalize_source_metadata_boundary

    inventory = active_names | removed_names
    visible = _restore_removed_image_positions(markdown, removed_positions or {}, removed_names)
    visible = normalize_source_metadata_boundary(visible, raw_markdown)
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


def _removed_image_positions(markdown: str, persisted: str, removed_names: set[str]) -> dict:
    """Keep removed-image placement outside the Markdown used for review and delivery."""
    untrimmed = MARKDOWN_IMAGE_RE.sub(
        lambda match: "" if _markdown_image_name(match.group(2)) in removed_names else match.group(0), markdown,
    )
    items = []
    offset = 0
    previous = 0
    for match in MARKDOWN_IMAGE_RE.finditer(markdown):
        offset += match.start() - previous
        name = _markdown_image_name(match.group(2))
        if name in removed_names:
            items.append({"name": name, "alt": match.group(1), "offset": offset,
                          "before": untrimmed[max(0, offset - 120):offset],
                          "after": untrimmed[offset:offset + 120]})
        else:
            offset += len(match.group(0))
        previous = match.end()
    return {"digest": hashlib.sha256(persisted.encode()).hexdigest(), "items": items,
            "trailing": untrimmed[len(untrimmed.rstrip()):]}


def _restore_removed_image_positions(markdown: str, positions: dict, removed_names: set[str]) -> str:
    unchanged = positions.get("digest") == hashlib.sha256(markdown.encode()).hexdigest()
    if unchanged:
        trailing = positions.get("trailing", "")
        if isinstance(trailing, str) and not trailing.strip():
            markdown = markdown.rstrip() + trailing
    present = {_markdown_image_name(match.group(2)) for match in MARKDOWN_IMAGE_RE.finditer(markdown)}
    insertions = []
    for item in positions.get("items", []):
        name = item.get("name")
        if name not in removed_names or name in present:
            continue
        offset = item.get("offset")
        if not unchanged:
            before, after = item.get("before", ""), item.get("after", "")
            context = before + after
            if not context or markdown.count(context) != 1:
                continue
            offset = markdown.index(context) + len(before)
        if not isinstance(offset, int) or not 0 <= offset <= len(markdown):
            continue
        insertions.append((offset, len(insertions), f'![{item.get("alt", name)}](assets/{name})'))
    for offset, _, image in sorted(insertions, reverse=True):
        markdown = markdown[:offset] + image + markdown[offset:]
    return markdown


def _persistable_reviewed_markdown(markdown: str, removed_names: set[str]) -> str:
    """Remove editor-only references to assets that remain in removed/."""
    from src.core.article_metadata import strip_editor_artifacts

    markdown = strip_editor_artifacts(markdown)
    for name in removed_names:
        markdown = _replace_image_target(markdown, name, None)
    return markdown.rstrip() + "\n"

