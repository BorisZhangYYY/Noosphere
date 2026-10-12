"""Free-form review prose with a fixed response protocol and trusted metadata."""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from src.core.review.review_validation import (
    H1_RE,
    HORIZONTAL_RULE_RE,
    SOURCE_METADATA_LINE_RE,
    extract_source_metadata_block,
)


TOKEN_RE = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}")
JSON_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)
SOURCE_FIELDS = ("Source", "Platform", "Author", "Published", "Captured", "Type")


@dataclass(frozen=True)
class MetadataCandidate:
    value: str
    evidence: str


@dataclass(frozen=True)
class ReviewPayload:
    title: str
    markdown: str
    summary: str
    metadata_candidates: dict[str, MetadataCandidate] = field(default_factory=dict)


def article_format_instruction(template: str, sections: Mapping[str, str] | None = None) -> str:
    """Read legacy variable templates as guidance without rewriting saved files."""
    if not template.strip():
        raise ValueError("Article format instructions must not be empty")
    fields = set(TOKEN_RE.findall(template))
    if not fields.intersection({"title", "source_metadata", *(sections or {})}):
        return template.strip()
    headings = sections or {}
    instructions = {
        "summary": "Summarize the main problem, conclusions and limitations in 3–5 substantive points.",
        "prerequisites": "Explain only background and terminology needed to understand the article.",
        "main_article": "Review the complete article, preserving its reasoning, evidence, code, tables, links and images.",
    }
    converted = re.sub(r"^\s*#\s*\{\{\s*title\s*\}\}\s*$", "", template, flags=re.MULTILINE)
    converted = re.sub(r"^\s*\{\{\s*source_metadata\s*\}\}\s*$", "", converted, flags=re.MULTILINE)

    def replace_field(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in {"title", "source_metadata"}:
            return ""
        return "(" + instructions.get(name, f"Write the content requested by the review perspective for {headings.get(name, name)}.") + ")"

    converted = TOKEN_RE.sub(replace_field, converted)
    return re.sub(r"\n{3,}", "\n\n", converted).strip()


def review_payload_instruction() -> str:
    """Keep the API envelope fixed while allowing any requested article format."""
    return (
        "# Response protocol\n\n"
        "Return exactly one JSON object. Do not return Markdown fences or prose outside JSON. "
        "Noosphere renders the title and trusted source metadata. Write the complete article body "
        "according to the article-format instructions, including its headings and separators. "
        "Do not repeat the top-level title or source metadata inside markdown.\n\n"
        "```json\n"
        "{\n"
        '  "title": "Reviewed article title",\n'
        '  "markdown": "Complete article body in Markdown",\n'
        '  "summary": "Internal factual article summary",\n'
        '  "metadata_candidates": {\n'
        '    "author": {"value": "Only when missing", "evidence": "Exact excerpt from the source"},\n'
        '    "published_at": null\n'
        "  }\n"
        "}\n"
        "```\n\n"
        "title, markdown and summary must be nonempty strings. summary is internal context: always return it, "
        "even when the article format says not to display a summary; do not add a visible summary against those instructions. "
        "This is the first text stage: preserve all existing local image references and their relative positions. "
        "Metadata candidates are optional and must be null unless the captured metadata is missing and the original "
        "article text contains explicit evidence. Copy a short evidence excerpt exactly; never infer from context."
    )


def parse_review_payload(response: str) -> ReviewPayload:
    """Validate response fields, without checking article section names or order."""
    data = parse_json_object(response)
    for name in ("title", "markdown", "summary"):
        if not isinstance(data.get(name), str) or not data[name].strip():
            raise ValueError(f"AI review payload requires a nonempty `{name}` string")
    title = " ".join(data["title"].split())
    markdown = clean_review_markdown(data["markdown"])
    if not markdown:
        raise ValueError("AI review payload has an empty article body")
    return ReviewPayload(
        title=title,
        markdown=markdown,
        summary=data["summary"].strip(),
        metadata_candidates=parse_metadata_candidates(data),
    )


def parse_metadata_candidates(data: Mapping[str, object]) -> dict[str, MetadataCandidate]:
    """Parse optional evidence-backed candidates without trusting them yet."""
    raw = data.get("metadata_candidates")
    if not isinstance(raw, dict):
        return {}
    candidates: dict[str, MetadataCandidate] = {}
    for response_key, internal_key in (("author", "author"), ("published_at", "publishedAt")):
        candidate = raw.get(response_key)
        if not isinstance(candidate, dict):
            continue
        value = str(candidate.get("value") or "").strip()
        evidence = str(candidate.get("evidence") or "").strip()
        if value and evidence:
            candidates[internal_key] = MetadataCandidate(value=value, evidence=evidence)
    return candidates


def serialize_metadata_candidates(candidates: Mapping[str, MetadataCandidate]) -> dict[str, dict[str, str]]:
    return {
        key: {"value": candidate.value, "evidence": candidate.evidence}
        for key, candidate in candidates.items()
    }


def parse_json_object(response: str) -> dict[str, object]:
    """Extract exactly one JSON object from a provider response."""
    candidate = response.strip()
    fenced = JSON_FENCE_RE.match(candidate)
    if fenced:
        candidate = fenced.group(1).strip()
    if not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            candidate = candidate[start : end + 1]
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"AI returned invalid structured review JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError("AI structured review payload must be a JSON object")
    return data


def trusted_source_metadata(source_markdown: str) -> str:
    """Build a canonical metadata block from captured data, never model output."""
    metadata = extract_source_metadata_block(source_markdown) or {}
    normalized: dict[str, str] = {}
    for key, value in metadata.items():
        clean_key = re.sub(r"[*_`]", "", key).strip().casefold()
        match = next((field for field in SOURCE_FIELDS if field.casefold() == clean_key), None)
        if match:
            normalized[match] = value.strip()
    return "\n".join(f"> {field}: {normalized.get(field) or 'Unknown'}" for field in SOURCE_FIELDS)


def normalize_source_metadata_boundary(markdown: str, source_markdown: str) -> str:
    """Keep trusted metadata contiguous and move misplaced content below its rule."""
    if not extract_source_metadata_block(source_markdown):
        return markdown

    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    h1_index = next(
        (index for index, line in enumerate(lines) if H1_RE.fullmatch(line.strip())),
        None,
    )
    if h1_index is None:
        return markdown

    rule_index = next(
        (
            index
            for index in range(h1_index + 1, len(lines))
            if HORIZONTAL_RULE_RE.fullmatch(lines[index])
        ),
        None,
    )
    if rule_index is None:
        return markdown

    displaced: list[str] = []
    for line in lines[h1_index + 1 : rule_index]:
        stripped = line.strip()
        if not stripped:
            continue
        match = SOURCE_METADATA_LINE_RE.fullmatch(stripped)
        if match:
            field = re.sub(r"[*_`]", "", match.group(1)).strip().casefold()
            if any(field == expected.casefold() for expected in SOURCE_FIELDS):
                continue
        displaced.append(line)

    tail = lines[rule_index + 1 :]
    while tail and not tail[0].strip():
        tail.pop(0)
    while displaced and not displaced[-1].strip():
        displaced.pop()

    rebuilt = [
        *lines[: h1_index + 1],
        "",
        *trusted_source_metadata(source_markdown).splitlines(),
        "",
        "---",
        "",
    ]
    if displaced:
        rebuilt.extend(displaced)
        rebuilt.append("")
    rebuilt.extend(tail)
    return "\n".join(rebuilt).rstrip() + "\n"


def render_review_payload(
    payload: ReviewPayload,
    source_markdown: str,
) -> str:
    body = clean_review_markdown(payload.markdown)
    if not body:
        raise ValueError("AI review payload has an empty article body")
    return f"# {payload.title}\n\n{trusted_source_metadata(source_markdown)}\n\n---\n\n{body}\n"


def clean_review_markdown(content: str) -> str:
    """Remove duplicate document headers, preserving body headings and quoted evidence."""
    cleaned = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    cleaned = re.sub(r"^#\s+[^\n]*(?:\n|$)\s*", "", cleaned, count=1)
    cleaned = re.sub(
        r"^(?:>\s*(?:Source|Platform|Author|Published|Captured|Type|来源|平台|作者|发布时间|抓取时间|类型)\s*[:：][^\n]*(?:\n|$)\s*)+",
        "", cleaned, flags=re.IGNORECASE,
    ).strip()
    cleaned = re.sub(r"^(?:---|\*\*\*|___)\s*(?:\n|$)\s*", "", cleaned, count=1)
    return cleaned.strip()
