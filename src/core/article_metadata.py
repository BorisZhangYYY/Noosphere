"""Protected source metadata and controlled enrichment for article workspaces."""
from __future__ import annotations

import re
from typing import Any

from src.core.review.review_validation import extract_source_metadata_block


FIELD_ORDER = ("Source", "Platform", "Author", "Published", "Captured", "Type")
ENRICHABLE_FIELDS = {"author": "Author", "publishedAt": "Published"}
_MISSING_VALUES = {"", "unknown", "未知", "none", "null", "n/a", "-"}
_H1_RE = re.compile(r"^#\s+\S")
_RULE_RE = re.compile(r"^\s{0,3}(?:-{3,}|_{3,}|\*{3,})\s*$")


def _missing(value: Any) -> bool:
    return str(value or "").strip().casefold() in _MISSING_VALUES


def _source_metadata(markdown: str) -> dict[str, str]:
    raw = extract_source_metadata_block(markdown) or {}
    return {
        re.sub(r"[*_`]", "", str(key)).strip().casefold(): str(value).strip()
        for key, value in raw.items()
    }


def editable_article_markdown(markdown: str) -> str:
    """Remove the leading canonical metadata block from content shown in the editor."""
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    h1_index = next((index for index, line in enumerate(lines) if _H1_RE.match(line.strip())), None)
    if h1_index is None:
        return normalized.rstrip() + "\n"
    rule_index = next(
        (index for index in range(h1_index + 1, min(len(lines), h1_index + 40)) if _RULE_RE.fullmatch(lines[index])),
        None,
    )
    if rule_index is None:
        return normalized.rstrip() + "\n"
    region = lines[h1_index + 1 : rule_index]
    if not any(
        line.lstrip().startswith(">")
        and ":" in line
        and re.sub(r"[*_`]", "", line.lstrip("> ").split(":", 1)[0]).strip().casefold()
        in {field.casefold() for field in FIELD_ORDER}
        for line in region
    ):
        return normalized.rstrip() + "\n"
    tail = lines[rule_index + 1 :]
    while tail and not tail[0].strip():
        tail.pop(0)
    return "\n".join([*lines[: h1_index + 1], "", *tail]).rstrip() + "\n"


def article_metadata_state(manifest: dict[str, Any], raw_markdown: str) -> dict[str, dict[str, Any]]:
    """Return canonical values plus the exact fields that may be enriched."""
    article = manifest.get("article") or {}
    source = _source_metadata(raw_markdown)
    enrichments = ((manifest.get("metadata_enrichment") or {}).get("fields") or {})

    url = str(article.get("url") or "")
    source_values = {
        "source": source.get("source") or (f"[{url}]({url})" if url else "Unknown"),
        "platform": str(article.get("platform_label") or source.get("platform") or article.get("platform") or "Unknown"),
        "author": str(article.get("author") or source.get("author") or ""),
        "publishedAt": str(article.get("published_at") or source.get("published") or ""),
        "capturedAt": str(article.get("captured_at") or source.get("captured") or "Unknown"),
        "contentType": str(article.get("content_type") or source.get("type") or "article"),
    }
    result: dict[str, dict[str, Any]] = {}
    for key, value in source_values.items():
        source_missing = key in ENRICHABLE_FIELDS and _missing(value)
        enrichment = enrichments.get(key) if isinstance(enrichments.get(key), dict) else {}
        enriched_value = str(enrichment.get("value") or "") if source_missing else ""
        result[key] = {
            "value": enriched_value or value or "Unknown",
            "editable": bool(source_missing and not enriched_value),
            "origin": str(enrichment.get("source") or "missing") if enriched_value else ("missing" if source_missing else "source"),
            "evidence": str(enrichment.get("evidence") or "") if enriched_value else "",
            "updatedAt": enrichment.get("updated_at") if enriched_value else None,
        }
    return result


def render_protected_review(
    content_markdown: str,
    manifest: dict[str, Any],
    raw_markdown: str,
) -> str:
    """Assemble editable prose with authoritative metadata for storage and export."""
    editable = editable_article_markdown(content_markdown)
    lines = editable.splitlines()
    h1_index = next((index for index, line in enumerate(lines) if _H1_RE.match(line.strip())), None)
    article = manifest.get("article") or {}
    title = str(article.get("title") or "Untitled").strip()
    if h1_index is None:
        heading = f"# {title}"
        body = editable.strip()
    else:
        heading = lines[h1_index].strip()
        body_lines = lines[h1_index + 1 :]
        while body_lines and not body_lines[0].strip():
            body_lines.pop(0)
        body = "\n".join(body_lines).strip()

    metadata = article_metadata_state(manifest, raw_markdown)
    canonical = {
        "Source": metadata["source"]["value"],
        "Platform": metadata["platform"]["value"],
        "Author": metadata["author"]["value"],
        "Published": metadata["publishedAt"]["value"],
        "Captured": metadata["capturedAt"]["value"],
        "Type": metadata["contentType"]["value"],
    }
    parts = [
        heading,
        "",
        *(f"> {field}: {canonical[field] or 'Unknown'}" for field in FIELD_ORDER),
        "",
        "---",
    ]
    if body:
        parts.extend(["", body])
    return "\n".join(parts).rstrip() + "\n"
