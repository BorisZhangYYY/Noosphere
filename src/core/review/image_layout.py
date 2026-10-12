"""Apply a text model's image operations without regenerating reviewed prose."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from src.core.review.image_filter import ImageFilterResult, _fenced_code_regions
from src.core.review.output_contract import parse_json_object
from src.integrations.assets import MARKDOWN_IMAGE_RE, split_image_target


@dataclass(frozen=True)
class ImageEntry:
    id: str
    path: str
    markdown: str
    source_order: int


@dataclass(frozen=True)
class BodyBlock:
    id: str
    start: int
    end: int
    text: str
    editable: bool
    indent: str = ""


@dataclass(frozen=True)
class ImageLayout:
    markdown: str
    removed_paths: set[str]
    operations: list[dict]
    text_edits: list[dict]


def image_matches(markdown: str):
    regions = _fenced_code_regions(markdown)
    return [match for match in MARKDOWN_IMAGE_RE.finditer(markdown)
            if not any(start <= match.start() < end for start, end in regions)]


def image_catalog(markdown: str, source_markdown: str, assets_dir: Path) -> list[ImageEntry]:
    """Assign source-order IDs only to currently referenced, downloaded assets."""
    active: dict[str, str] = {}
    for match in image_matches(markdown):
        target, _ = split_image_target(match.group(2))
        path = target.removeprefix("./")
        local = (assets_dir.parent / path).resolve()
        if local.is_relative_to(assets_dir.resolve()) and local.is_file():
            active.setdefault(path, match.group(0))
    source_paths: list[str] = []
    for match in image_matches(source_markdown):
        path = split_image_target(match.group(2))[0].removeprefix("./")
        if path not in source_paths:
            source_paths.append(path)
    source_paths.extend(path for path in active if path not in source_paths)
    return [ImageEntry(f"image_{index:03d}", path, active[path], index)
            for index, path in enumerate(source_paths, 1) if path in active]


def body_blocks(markdown: str) -> list[BodyBlock]:
    """Identify prose and list-item boundaries while protecting the document header."""
    header = re.match(r"\A# [^\n]+\n\s*(?:>[^\n]*\n)+\s*---[^\n]*\n", markdown)
    body_start = header.end() if header else 0
    if not header and markdown.startswith("# "):
        body_start = markdown.find("\n") + 1
    regions = _fenced_code_regions(markdown)
    lines = list(re.finditer(r"[^\n]+(?:\n|$)|\n", markdown[body_start:]))
    spans: list[tuple[int, int]] = []
    pending: int | None = None
    for line in lines:
        start, end = body_start + line.start(), body_start + line.end()
        text = line.group().rstrip("\n")
        fenced = any(a <= start < b for a, b in regions)
        boundary = bool(re.match(r"^\s{0,3}(?:#{1,6} |(?:[-+*]|\d+[.)])\s+)", text))
        if not fenced and (not text.strip() or boundary):
            if pending is not None:
                spans.append((pending, start))
                pending = None
            if not text.strip():
                continue
        if pending is None:
            pending = start
        if not fenced and re.match(r"^#{1,6} ", text):
            spans.append((pending, end))
            pending = None
    if pending is not None:
        spans.append((pending, len(markdown)))
    blocks: list[BodyBlock] = []
    for start, end in spans:
        while end > start and markdown[end - 1] in "\n\r":
            end -= 1
        text = markdown[start:end]
        if not text.strip() or not MARKDOWN_IMAGE_RE.sub("", text).strip():
            continue
        structural = re.search(r"(?m)^\s*(?:#|>|```|~~~|\||---\s*$|\*\*\*\s*$|___\s*$)", text)
        editable = not structural
        if any(a < end and start < b for a, b in regions):
            continue
        marker = re.match(r"^(\s*(?:[-+*]|\d+[.)])\s+)", text)
        blocks.append(BodyBlock(f"block_{len(blocks) + 1:03d}", start, end, text,
                                bool(editable), " " * len(marker.group(1)) if marker else ""))
    return blocks


def layout_context(markdown: str, source_markdown: str, assets_dir: Path,
                   analysis: ImageFilterResult | None, summary: str) -> tuple[str, list[ImageEntry], list[BodyBlock]]:
    catalog = image_catalog(markdown, source_markdown, assets_dir)
    blocks = body_blocks(markdown)
    preview_size = max(40, 14000 // max(len(blocks), 1))
    block_records = [{"id": block.id, "text": block.text[:preview_size],
                      "truncated": len(block.text) > preview_size,
                      "editable": block.editable and len(block.text) <= preview_size} for block in blocks]
    images = []
    for entry in catalog:
        occurrences = [match.start() for match in image_matches(markdown)
                       if split_image_target(match.group(2))[0].removeprefix("./") == entry.path]
        locations = []
        for position in occurrences:
            previous = [block for block in blocks if block.start <= position]
            if previous:
                locations.append(previous[-1].id)
        images.append({"id": entry.id, "path": entry.path, "source_order": entry.source_order,
                       "current_blocks": locations, "reference": entry.markdown,
                       "recommendation": ("remove" if entry.path in analysis.promotion_images else
                                          "keep" if entry.path in analysis.relevant_images else "unknown") if analysis else "unknown",
                       "description": analysis.image_descriptions.get(entry.path, "Unknown") if analysis else "Unknown",
                       "function": analysis.image_functions.get(entry.path, "Unknown") if analysis else "Unknown",
                       "vision_failed": analysis is None or entry.path in analysis.failed_images})
    visible = {record["id"] for record in block_records if record["editable"]}
    blocks = [BodyBlock(block.id, block.start, block.end, block.text, block.id in visible, block.indent)
              for block in blocks]
    return json.dumps({"summary": summary, "blocks": block_records, "images": images}, ensure_ascii=False), catalog, blocks


def apply_image_layout(markdown: str, response: str, catalog: list[ImageEntry], blocks: list[BodyBlock]) -> ImageLayout:
    """Validate a closed operation set, then preserve every untouched source byte."""
    data = parse_json_object(response)
    operations, edits = data.get("images"), data.get("text_edits", [])
    if not isinstance(operations, list) or not isinstance(edits, list):
        raise ValueError("Image layout must contain images and text_edits lists")
    entries = {entry.id: entry for entry in catalog}
    anchors = {block.id: block for block in blocks}
    seen: set[str] = set()
    removed: set[str] = set()
    patches: list[tuple[int, int, str]] = []
    insertions: dict[int, list[str]] = {}
    changed_paths: set[str] = set()
    related_blocks: set[str] = set()
    for operation in operations:
        if not isinstance(operation, dict) or operation.get("id") not in entries or operation["id"] in seen:
            raise ValueError("Image layout contains an unknown or duplicate image ID")
        seen.add(operation["id"])
        entry = entries[operation["id"]]
        action = operation.get("action")
        if action not in {"keep", "move", "remove"}:
            raise ValueError("Image actions must be keep, move or remove")
        if action == "keep":
            continue
        if not isinstance(operation.get("reason"), str) or not operation["reason"].strip():
            raise ValueError("Image changes require a reason")
        changed_paths.add(entry.path)
        if action == "remove":
            removed.add(entry.path)
        else:
            anchor = anchors.get(operation.get("target"))
            side = operation.get("side", "after")
            if anchor is None or side not in {"before", "after"}:
                raise ValueError("Image movement requires a valid body block and side")
            position = anchor.start if side == "before" else anchor.end
            related_blocks.add(anchor.id)
            indent = anchor.indent if side == "after" else ""
            insertions.setdefault(position, []).append(indent + entry.markdown)
    if seen != set(entries):
        raise ValueError("Image layout must account for every catalog image exactly once")
    for match in image_matches(markdown):
        path = split_image_target(match.group(2))[0].removeprefix("./")
        if path in changed_paths:
            patches.append((match.start(), match.end(), ""))
            previous = [block for block in blocks if block.start <= match.start()]
            following = [block for block in blocks if block.end >= match.end()]
            related_blocks.update(block.id for block in previous[-1:] + following[:1])
    edited: set[str] = set()
    edited_ranges: list[tuple[int, int]] = []
    for edit in edits:
        if not isinstance(edit, dict):
            raise ValueError("Invalid local text edit")
        anchor = anchors.get(edit.get("id"))
        text, reason = edit.get("text"), edit.get("reason")
        if (anchor is None or not anchor.editable or anchor.id in edited or
                not isinstance(text, str) or not text.strip() or not isinstance(reason, str) or not reason.strip()):
            raise ValueError("Text edits require a unique editable body block, text and reason")
        if not changed_paths:
            raise ValueError("Text edits require an image change")
        if anchor.id not in related_blocks:
            raise ValueError("Local text edits must relate to an image operation")
        retained_refs = [match for match in image_matches(anchor.text)
                         if split_image_target(match.group(2))[0].removeprefix("./") not in changed_paths]
        if retained_refs:
            raise ValueError("Local text edits cannot discard images marked keep")
        if MARKDOWN_IMAGE_RE.search(text) or re.search(r"(?m)^\s*(?:#|>|```|~~~|\||---\s*$)", text):
            raise ValueError("Local text edits cannot add images, metadata or structural blocks")
        if "\n\n" in text:
            raise ValueError("A local text edit must remain one body block")
        marker = re.match(r"^\s*(?:[-+*]|\d+[.)])\s+", anchor.text)
        replacement_marker = re.match(r"^\s*(?:[-+*]|\d+[.)])\s+", text)
        if (marker.group() if marker else None) != (replacement_marker.group() if replacement_marker else None):
            raise ValueError("Local text edits must preserve list markers")
        edited.add(anchor.id)
        edited_ranges.append((anchor.start, anchor.end))
        patches.append((anchor.start, anchor.end, text))
    patches = [(start, end, replacement) for start, end, replacement in patches
               if replacement or not any(a <= start and end <= b for a, b in edited_ranges)]
    patches.sort()
    if any(left[1] > right[0] for left, right in zip(patches, patches[1:])):
        raise ValueError("Overlapping image and text edits")
    for position, refs in insertions.items():
        if any(start < position < end for start, end, _ in patches):
            raise ValueError("Image insertion overlaps a replacement")
        separator = "\n\n"
        patches.append((position, position, separator + separator.join(refs) + separator))
    result = markdown
    for start, end, replacement in sorted(patches, key=lambda item: (item[0], item[1]), reverse=True):
        result = result[:start] + replacement + result[end:]
    return ImageLayout(result, removed, operations, edits)
