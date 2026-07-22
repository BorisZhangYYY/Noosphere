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
