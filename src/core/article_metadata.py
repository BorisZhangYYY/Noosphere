"""Protected source metadata and controlled enrichment for article workspaces."""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.core.review.review_validation import extract_source_metadata_block


FIELD_ORDER = ("Source", "Platform", "Author", "Published", "Captured", "Type")
ENRICHABLE_FIELDS = {"author": "Author", "publishedAt": "Published"}
_MISSING_VALUES = {"", "unknown", "未知", "none", "null", "n/a", "-"}
_H1_RE = re.compile(r"^#\s+\S")
_RULE_RE = re.compile(r"^\s{0,3}(?:-{3,}|_{3,}|\*{3,})\s*$")
_EDITOR_IMAGE_ACTION_RE = re.compile(
    r"""[ \t]*<button\b[^>]*\bclass\s*=\s*["'][^"']*\bnoosphere-image-action\b[^"']*["'][^>]*>.*?</button>[ \t]*\n?""",
    flags=re.IGNORECASE | re.DOTALL,
)


def _missing(value: Any) -> bool:
    return str(value or "").strip().casefold() in _MISSING_VALUES


def _source_metadata(markdown: str) -> dict[str, str]:
    raw = extract_source_metadata_block(markdown) or {}
    return {
        re.sub(r"[*_`]", "", str(key)).strip().casefold(): str(value).strip()
        for key, value in raw.items()
    }


def strip_editor_artifacts(markdown: str) -> str:
    """Remove UI-only controls that must never enter reviewed Markdown."""
    return _EDITOR_IMAGE_ACTION_RE.sub("", markdown)


def editable_article_markdown(markdown: str) -> str:
    """Remove the leading canonical metadata block from content shown in the editor."""
    normalized = strip_editor_artifacts(markdown).replace("\r\n", "\n").replace("\r", "\n")
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
            "model": str(enrichment.get("model") or "") if enriched_value else "",
            "provider": str(enrichment.get("provider") or "") if enriched_value else "",
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


def apply_ai_metadata_candidates(
    manifest_path: Path,
    raw_markdown: str,
    reviewed_markdown: str,
    candidates: dict[str, dict[str, str]],
    *,
    model: str,
    provider: str,
) -> tuple[str, list[dict[str, str]]]:
    """Accept only evidence-backed candidates for still-empty source fields."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    enrichment = manifest.setdefault("metadata_enrichment", {})
    fields = enrichment.setdefault("fields", {})
    history = enrichment.setdefault("history", [])
    state = article_metadata_state(manifest, raw_markdown)
    source_evidence = " ".join(raw_markdown.split()).casefold()
    now = datetime.now(UTC).isoformat()
    outcomes: list[dict[str, str]] = []

    for key in ("author", "publishedAt"):
        candidate = candidates.get(key)
        if not isinstance(candidate, dict):
            continue
        value = str(candidate.get("value") or "").strip()
        evidence = str(candidate.get("evidence") or "").strip()
        if not value or not evidence:
            continue
        reason = ""
        if state[key]["origin"] == "source":
            reason = "captured source value is protected"
        elif isinstance(fields.get(key), dict) and str(fields[key].get("value") or "").strip():
            reason = "field was already enriched"
        elif len(" ".join(evidence.split())) < 4 or " ".join(evidence.split()).casefold() not in source_evidence:
            reason = "evidence was not found verbatim in the captured article"
        elif not _value_supported_by_evidence(value, evidence):
            reason = "candidate value was not supported by its evidence"

        if reason:
            action = "reverted"
        else:
            action = "accepted"
            fields[key] = {
                "value": value,
                "source": "ai",
                "evidence": evidence,
                "model": model,
                "provider": provider,
                "updated_at": now,
            }
        record = {
            "field": key,
            "action": action,
            "source": "ai",
            "value": value,
            "previous_value": str((fields.get(key) or {}).get("value") or "") if action == "reverted" else "",
            "evidence": evidence,
            "model": model,
            "provider": provider,
            "reason": reason,
            "at": now,
        }
        history.append(record)
        outcomes.append({key: str(value) for key, value in record.items()})

    if outcomes:
        _atomic_write_json(manifest_path, manifest)
    return render_protected_review(reviewed_markdown, manifest, raw_markdown), outcomes


def _value_supported_by_evidence(value: str, evidence: str) -> bool:
    date_match = re.fullmatch(r"\s*(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?\s*", value)
    if date_match:
        year, month, day = (str(int(part)) for part in date_match.groups())
        evidence_folded = evidence.casefold()
        evidence_numbers = {str(int(part)) for part in re.findall(r"\d+", evidence_folded)}
        month_names = (
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
        )
        month_supported = month in evidence_numbers or month_names[int(month) - 1] in evidence_folded
        return year in evidence_numbers and day in evidence_numbers and month_supported

    def tokens(text: str) -> list[str]:
        values = re.findall(r"[\w\u3400-\u9fff]+", text.casefold(), flags=re.UNICODE)
        return [item.lstrip("0") or "0" if item.isdigit() else item for item in values]

    candidate_tokens = tokens(value)
    evidence_tokens = set(tokens(evidence))
    return bool(candidate_tokens) and all(token in evidence_tokens for token in candidate_tokens)


def _atomic_write_json(destination: Path, payload: dict[str, Any]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}-", dir=destination.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, destination)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
