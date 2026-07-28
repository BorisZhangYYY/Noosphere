from __future__ import annotations

import pytest

from src.core.config.schema import ReviewPerspectiveConfig
from src.core.review.output_contract import (
    materialize_review_output,
    normalize_source_metadata_boundary,
    parse_review_payload,
    validate_output_template,
)


TEMPLATE = """# {{title}}

{{source_metadata}}

---

## AI Summary

{{summary}}

---

## Main Article

{{main_article}}
"""


def test_contract_materializes_exact_template_without_duplicate_rules() -> None:
    response = """# Example

> Source: [https://example.com](https://example.com)
> Platform: Web
> Author: Lin
> Published: 2026-07-01
> Captured: 2026-07-21
> Type: article

---

## AI Summary

- Summary

---

## Main Article

Body with `code`.
"""
    rendered = materialize_review_output(
        response,
        TEMPLATE,
        {"summary": "AI Summary", "main_article": "Main Article"},
    )

    assert rendered.count("## AI Summary") == 1
    assert rendered.count("## Main Article") == 1
    assert rendered.count("\n---\n") == 2
    assert "{{" not in rendered
    assert "Body with `code`." in rendered


def test_contract_rejects_templates_missing_content_slots() -> None:
    with pytest.raises(ValueError, match="missing fields"):
        validate_output_template("# {{title}}", {"summary": "AI Summary"})


def test_contract_requires_each_template_field_exactly_once() -> None:
    template = TEMPLATE.replace("{{summary}}", "{{summary}}\n\n{{summary}}")

    with pytest.raises(ValueError, match="exactly once"):
        validate_output_template(template, {"summary": "AI Summary", "main_article": "Main Article"})


def test_legacy_perspective_config_is_upgraded() -> None:
    profile = ReviewPerspectiveConfig.model_validate({
        "label": "Original",
        "prompt_path": "prompts/perspectives/original.md",
        "template_path": "prompts/edit_article.md",
    })

    assert profile.template_path == "prompts/templates/original_article.md"
    assert profile.output_sections["main_article"] == "Main Article"


def test_structured_payload_uses_trusted_metadata_and_reserves_top_level_headings() -> None:
    response = '''{
      "title": "A clearer title",
      "slots": {
        "summary": "Short summary.",
        "main_article": "## Model tried to own structure\\n\\nBody."
      }
    }'''
    source = """# Original

> Source: [https://example.com](https://example.com)
> Platform: Web
> Captured: 2026-07-22
> Type: article

---

Original body.
"""

    rendered = materialize_review_output(
        response,
        TEMPLATE,
        {"summary": "AI Summary", "main_article": "Main Article"},
        source_markdown=source,
    )

    assert rendered.startswith("# A clearer title")
    assert "> Author: Unknown" in rendered
    assert "> Published: Unknown" in rendered
    assert "### Model tried to own structure" in rendered
    assert rendered.count("## Main Article") == 1


def test_structured_payload_keeps_evidence_candidates_separate_from_markdown() -> None:
    payload = parse_review_payload(
        '''{
          "title": "Reviewed title",
          "slots": {"summary": "Summary", "main_article": "Body"},
          "metadata_candidates": {
            "author": {"value": "Ada Lovelace", "evidence": "Written by Ada Lovelace"},
            "published_at": null
          }
        }''',
        {"summary": "AI Summary", "main_article": "Main Article"},
    )

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
