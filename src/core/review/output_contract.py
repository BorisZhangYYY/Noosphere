"""Structured review payloads and deterministic Markdown rendering.

The model owns prose only. Noosphere owns the title/metadata/section skeleton so
provider formatting quirks can never corrupt the final document contract.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

from src.core.review.ai_review_data import strip_markdown_fence
from src.core.review.review_validation import H1_RE, extract_source_metadata_block


TOKEN_RE = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}")
JSON_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)
TRAILING_RULE_RE = re.compile(r"(?:^|\n)\s*(?:---|\*\*\*|___)\s*$")
SOURCE_FIELDS = ("Source", "Platform", "Author", "Published", "Captured", "Type")


@dataclass(frozen=True)
class ReviewPayload:
    title: str
    slots: dict[str, str]


def validate_output_template(template: str, sections: Mapping[str, str]) -> None:
    required = {"title", "source_metadata", *sections.keys()}
    present = set(TOKEN_RE.findall(template))
    missing = sorted(required - present)
    unknown = sorted(present - required)
    if missing:
        raise ValueError(f"Output template is missing fields: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"Output template contains unknown fields: {', '.join(unknown)}")
    duplicated = sorted(token for token in required if len(re.findall(r"\{\{\s*" + re.escape(token) + r"\s*\}\}", template)) != 1)
    if duplicated:
        raise ValueError(f"Output template fields must appear exactly once: {', '.join(duplicated)}")


def review_payload_instruction(sections: Mapping[str, str]) -> str:
    """Return a provider-neutral JSON contract for the prose slots."""
    slot_example = ",\n".join(f'      "{name}": "Markdown content for {heading}"' for name, heading in sections.items())
    required = ", ".join(f'`{name}`' for name in sections)
    return (
        "# Response protocol\n\n"
        "Return exactly one JSON object. Do not return Markdown fences or prose outside JSON. "
        "Noosphere renders the final title, trusted source metadata, headings, and separators. "
        "You only write the title and content slots. Markdown is allowed inside each string.\n\n"
        "```json\n"
        "{\n"
        '  "title": "Reviewed article title",\n'
        '  "slots": {\n'
        f"{slot_example}\n"
        "  }\n"
        "}\n"
        "```\n\n"
        f"All slots are required: {required}. Preserve local image references exactly when they are relevant."
    )


def parse_review_payload(response: str, sections: Mapping[str, str]) -> ReviewPayload:
    """Parse the model's JSON payload without accepting a second Markdown format."""
    data = parse_json_object(response)
    title = str(data.get("title") or "").strip()
    raw_slots = data.get("slots")
    if not isinstance(raw_slots, dict):
        raise ValueError("AI structured review payload is missing the `slots` object")
    slots = {name: sanitize_slot_markdown(str(raw_slots.get(name) or "")) for name in sections}
    missing = [name for name, value in slots.items() if not value]
    if missing:
        raise ValueError(f"AI structured review payload has empty slots: {', '.join(missing)}")
    if not title:
        raise ValueError("AI structured review payload has an empty title")
    return ReviewPayload(title=title, slots=slots)


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


def render_review_payload(
    payload: ReviewPayload,
    template: str,
    sections: Mapping[str, str],
    source_markdown: str,
) -> str:
    validate_output_template(template, sections)
    values = {
        "title": payload.title,
        "source_metadata": trusted_source_metadata(source_markdown),
        **payload.slots,
    }
    rendered = TOKEN_RE.sub(lambda match: values.get(match.group(1), ""), template)
    return rendered.strip() + "\n"


def sanitize_slot_markdown(content: str) -> str:
    """Keep slot Markdown expressive while reserving H1/H2 for the renderer."""
    lines: list[str] = []
    in_fence = False
    fence = ""
    for line in content.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not in_fence:
                in_fence, fence = True, marker
            elif marker == fence:
                in_fence, fence = False, ""
            lines.append(line)
            continue
        if not in_fence:
            match = re.match(r"^(\s*)#{1,2}\s+(.+)$", line)
            if match:
                line = f"{match.group(1)}### {match.group(2)}"
        lines.append(line)
    cleaned = "\n".join(lines).strip()
    while cleaned and (match := TRAILING_RULE_RE.search(cleaned)):
        cleaned = cleaned[: match.start()].rstrip()
    return cleaned


def materialize_review_output(
    response: str,
    template: str,
    sections: Mapping[str, str],
    source_markdown: str | None = None,
) -> str:
    """Compatibility entrypoint, now preferring the structured payload contract."""
    if source_markdown is not None:
        return render_review_payload(parse_review_payload(response, sections), template, sections, source_markdown)

    # Legacy callers/tests may still pass full Markdown. This branch is not used by
    # the pipeline and can be removed once external integrations migrate.
    markdown = strip_markdown_fence(response)
    title_match = H1_RE.search(markdown)
    title = title_match.group(1).strip() if title_match else "Untitled"
    from src.core.review.review_validation import section_body

    payload = ReviewPayload(
        title=title,
        slots={name: sanitize_slot_markdown(section_body(markdown, 2, heading)) for name, heading in sections.items()},
    )
    return render_review_payload(payload, template, sections, markdown)
