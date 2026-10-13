from __future__ import annotations

import json

import pytest

from src.core.config.schema import PipelineConfig, ReviewPerspectiveConfig
from src.core.review.output_contract import (
    article_format_instruction,
    normalize_source_metadata_boundary,
    parse_review_payload,
    render_review_payload,
)


SOURCE = """# Original

> Source: [https://example.com](https://example.com)
> Platform: Web
> Captured: 2026-07-22
> Type: article

---

Original body.
"""


def test_free_form_markdown_preserves_requested_headings_code_and_separators() -> None:
    body = '## Findings\n\nBody.\n\n---\n\n## Details\n\n```python\nprint("example")\n```'
    payload = parse_review_payload(json.dumps({
        "title": "Reviewed title", "markdown": body, "summary": "Internal summary",
    }))
    rendered = render_review_payload(payload, SOURCE)

    assert rendered.startswith("# Reviewed title")
    assert "> Author: Unknown" in rendered
    assert "> Published: Unknown" in rendered
    assert body in rendered
    assert "AI Summary" not in rendered
    assert "Internal summary" not in rendered


def test_duplicate_headers_do_not_replace_trusted_metadata_or_body_quotes() -> None:
    body = "# Duplicate\n\n> Author: Invented\n> Type: invented\n\n---\n\n## Evidence\n\n> Author: A quoted statement in the article."
    payload = parse_review_payload(json.dumps({
        "title": "Reviewed title", "markdown": body, "summary": "Summary",
    }))
    rendered = render_review_payload(payload, SOURCE)

    assert "Duplicate" not in rendered
    assert "Invented" not in rendered
    assert "> Type: article" in rendered
    assert "> Author: A quoted statement in the article." in rendered
    assert "## Evidence" in rendered


@pytest.mark.parametrize("field,value", [
    ("title", ""), ("markdown", "  "), ("summary", ""),
    ("markdown", {"body": "text"}), ("summary", None),
])
def test_response_protocol_requires_nonempty_strings(field, value) -> None:
    data = {"title": "Title", "markdown": "Body", "summary": "Summary"}
    data[field] = value
    with pytest.raises(ValueError, match=field):
        parse_review_payload(json.dumps(data))


def test_response_protocol_rejects_a_body_containing_only_duplicate_headers() -> None:
    with pytest.raises(ValueError, match="empty article body"):
        parse_review_payload(json.dumps({
            "title": "Title", "markdown": "# Title\n\n> Author: Ada\n\n---", "summary": "Summary",
        }))


def test_natural_article_format_has_no_mandatory_fields_or_sections() -> None:
    template = "Only output the complete article, with its original headings. Do not add a summary."
    assert article_format_instruction(template) == template


def test_natural_format_keeps_literal_template_expressions_in_code_examples() -> None:
    template = "Preserve examples such as `Hello {{name}}` and explain their meaning."
    assert article_format_instruction(template) == template


def test_legacy_variables_become_writing_guidance_and_keep_custom_headings() -> None:
    template = "# {{title}}\n\n{{source_metadata}}\n\n---\n\n## Main Article\n\n{{main_article}}\n\n## Takeaways\n\n{{custom_notes}}"
    converted = article_format_instruction(template, {"custom_notes": "Takeaways"})

    assert "{{" not in converted
    assert "## Main Article" in converted
    assert "## Takeaways" in converted
    assert "complete article" in converted
    assert "Takeaways" in converted
    assert "source_metadata" not in converted


def test_template_leading_rules_are_not_read_as_yaml_frontmatter(tmp_path) -> None:
    template = "---\n\n## Quick understanding\n\n(Explain the main result.)\n\n---\n\n## Full article"
    template_file = tmp_path / "template.md"
    template_file.write_text(template, encoding="utf-8")
    config = PipelineConfig(perspectives={"custom": ReviewPerspectiveConfig(
        label="Custom", prompt_path="prompts/perspectives/original.md", template_path=str(template_file),
    )})

    assert config.resolve_review_contract("custom")[1] == template
    assert "## Quick understanding" in config.resolve_review_prompt("custom")[0]


def test_legacy_perspective_config_is_upgraded_without_section_validation() -> None:
    profile = ReviewPerspectiveConfig.model_validate({
        "label": "Original", "prompt_path": "prompts/perspectives/original.md",
        "template_path": "prompts/edit_article.md", "output_sections": {"main_article": "Main Article"},
    })
    assert profile.template_path == "prompts/templates/original_article.md"
    assert "output_sections" not in profile.model_dump()
    assert "body_section" not in profile.model_dump()
    assert len(profile.prompt_metadata().required_headings) == 1


def test_structured_payload_keeps_evidence_candidates_separate_from_markdown() -> None:
    payload = parse_review_payload(json.dumps({
        "title": "Reviewed title", "markdown": "Body", "summary": "Summary",
        "metadata_candidates": {
            "author": {"value": "Ada Lovelace", "evidence": "Written by Ada Lovelace"},
            "published_at": None,
        },
    }))
    assert payload.metadata_candidates["author"].value == "Ada Lovelace"
    assert payload.metadata_candidates["author"].evidence == "Written by Ada Lovelace"
    assert "publishedAt" not in payload.metadata_candidates


def test_metadata_boundary_moves_misplaced_image_below_type_and_rule() -> None:
    source = """# Original

> Source: [https://example.com](https://example.com)
> Platform: Web
> Author: Lin
> Published: 2026-07-01
> Captured: 2026-07-23T00:00:00+00:00
> Type: article

---

![Cover](assets/cover.png)

Original body.
"""
    malformed = """# Reviewed

> Source: [https://example.com](https://example.com)
> Platform: Web
> Author: Lin
> Published: 2026-07-01
> Captured: 2026-07-23T00:00:00+00:00

![Cover](assets/cover.png)

> Type: article

---

## AI Summary

Summary.
"""

    normalized = normalize_source_metadata_boundary(malformed, source)

    metadata = (
        "> Source: [https://example.com](https://example.com)\n"
        "> Platform: Web\n"
        "> Author: Lin\n"
        "> Published: 2026-07-01\n"
        "> Captured: 2026-07-23T00:00:00+00:00\n"
        "> Type: article"
    )
    assert metadata in normalized
    assert normalized.count("> Type: article") == 1
    assert normalized.index("> Type: article") < normalized.index("---")
    assert normalized.index("---") < normalized.index("assets/cover.png")
    assert normalized.index("assets/cover.png") < normalized.index("## AI Summary")
