from src.core.review.image_filter import ensure_relevant_images_present


def test_missing_source_image_is_restored_before_following_prose() -> None:
    raw = """# Title

![Header](assets/header.png)

Platform chrome that the reviewer removes.

This is the first real paragraph and it survives the review intact.
"""
    reviewed = """# Title

## Main

This is the first real paragraph and it survives the review intact.
"""

    restored = ensure_relevant_images_present(
        reviewed,
        {"assets/header.png"},
        raw_markdown=raw,
    )

    assert restored.count("assets/header.png") == 1
    assert restored.index("assets/header.png") < restored.index("This is the first real paragraph")


def test_unanchored_source_image_is_preserved_without_model_cooperation() -> None:
    restored = ensure_relevant_images_present(
        "# Title\n\n## Main\n\nCompletely rewritten body.\n",
        {"assets/diagram.png"},
        raw_markdown="![Diagram](assets/diagram.png)",
    )

    assert "![diagram](assets/diagram.png)" in restored


def test_lead_image_stays_after_complete_metadata_and_separator() -> None:
    raw = """# Title

> Source: https://example.com
> Platform: Web
> Captured: 2026-07-23T00:00:00+00:00
> Type: article

---

![Cover](assets/cover.png)

Publisher chrome
"""
    reviewed = """# Reviewed

> Source: https://example.com
> Platform: Web
> Author: Unknown
> Captured: 2026-07-23T00:00:00+00:00
> Type: article

---

## Summary

Reviewed prose.
"""

    restored = ensure_relevant_images_present(
        reviewed,
        {"assets/cover.png"},
        raw_markdown=raw,
    )

    assert restored.index("> Type: article") < restored.index("assets/cover.png")
    assert restored.index("---") < restored.index("assets/cover.png")
    assert restored.index("assets/cover.png") < restored.index("## Summary")
