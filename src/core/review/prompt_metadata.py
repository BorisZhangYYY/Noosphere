"""Parse YAML frontmatter from prompt files to extract validation rules.

Prompt files may contain a YAML frontmatter block at the top (delimited by
`---` lines) that specifies output format requirements and validation rules.
The remainder of the file is the actual prompt text sent to the AI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class RequiredHeading:
    """One heading that the output must contain."""

    level: int
    text: str | None


@dataclass
class ValidationRule:
    """A single validation rule extracted from prompt metadata."""

    rule_type: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class PromptMetadata:
    """Structured metadata from a prompt file's YAML frontmatter."""

    required_headings: list[RequiredHeading] = field(default_factory=list)
    validation_rules: list[ValidationRule] = field(default_factory=list)

    @property
    def has_no_content_before_rule(self) -> str | None:
        """Return the heading name that must have no content before it, if any."""
        for rule in self.validation_rules:
            if rule.rule_type == "no_content_before_heading":
                return rule.params.get("heading")
        return None

    @property
    def requires_all_images_local(self) -> bool:
        """Whether the prompt requires all images to use local paths."""
        for rule in self.validation_rules:
            if rule.rule_type == "all_images_local":
                return rule.params.get("required", True)
        return False


@dataclass
class ParsedPrompt:
    """A prompt file split into metadata and body text."""

    metadata: PromptMetadata
    body: str


def parse_prompt_file(path: Path) -> ParsedPrompt:
    """Read a prompt file and split it into YAML frontmatter + Markdown body."""
    text = path.read_text(encoding="utf-8")
    return parse_prompt(text)


def parse_prompt(text: str) -> ParsedPrompt:
    """Split a prompt string into YAML frontmatter + Markdown body.

    Frontmatter is delimited by `---` on its own line at the very start
    and a matching `---` on its own line that ends the block.
    """
    lines = text.replace("\r\n", "\n").split("\n")

    if not lines or lines[0].strip() != "---":
        return ParsedPrompt(metadata=PromptMetadata(), body=text)

    # Find the closing ---
    end_index = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_index = i
            break

    if end_index is None:
        return ParsedPrompt(metadata=PromptMetadata(), body=text)

    frontmatter_text = "\n".join(lines[1:end_index])
    body = "\n".join(lines[end_index + 1 :]).strip()

    metadata = _parse_frontmatter(frontmatter_text)
    return ParsedPrompt(metadata=metadata, body=body)


def _parse_frontmatter(text: str) -> PromptMetadata:
    """Parse YAML frontmatter text into PromptMetadata."""
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return PromptMetadata()

    if not isinstance(data, dict):
        return PromptMetadata()

    output_format = data.get("output_format", {})
    required_headings: list[RequiredHeading] = []
    for heading in output_format.get("required_headings", []):
        if isinstance(heading, dict):
            level = heading.get("level", 1)
            text_value = heading.get("text")
            # null means "any H1 title" — the validator only checks level
            required_headings.append(
                RequiredHeading(level=int(level), text=text_value if text_value is not None else None)
            )

    validation_rules: list[ValidationRule] = []
    for rule in output_format.get("validation_rules", []):
        if isinstance(rule, dict):
            for key, value in rule.items():
                params = _normalize_rule_params(key, value)
                validation_rules.append(ValidationRule(rule_type=key, params=params))

    return PromptMetadata(required_headings=required_headings, validation_rules=validation_rules)


def _normalize_rule_params(rule_type: str, value: Any) -> dict[str, Any]:
    """Convert a frontmatter rule value into a consistent params dict."""
    del rule_type  # reserved for future rule-specific normalization
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        return {"heading": value}
    return {"required": bool(value)}
