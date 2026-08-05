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


def test_restored_image_is_never_inserted_inside_code_fence() -> None:
    raw = """# Title

你可以直接用一句Prompt，把它装到你的Agent里面。

```
帮我安装这个skill：https://github.com/KKKKhazix/human-writing
```

装好之后，你就可以正式调用它了。我就调用了这个Skill，直接描述了一下，然后这次我特意强调，用语音的方式记日记。![Image](assets/image_04.png)当你把你的需求发给它之后，它就会进行思考、查证等等等等。
"""
    reviewed = """# Title

你可以直接用一句Prompt，把它装到你的Agent里面。

```
帮我安装这个skill：https://github.com/KKKKhazix/human-writing
```

装好之后，你就可以正式调用它了。

我就调用了这个Skill，直接描述了一下，然后这次我特意强调，用语音的方式记日记。

当你把你的需求发给它之后，它就会进行思考、查证等等等等。
"""

    restored = ensure_relevant_images_present(
        reviewed,
        {"assets/image_04.png"},
        raw_markdown=raw,
    )

    closing_fence = restored.index("```", restored.index("```") + 3)
    image_pos = restored.index("assets/image_04.png")
    assert image_pos > closing_fence
    assert restored.index("用语音的方式记日记。") < image_pos


def test_images_sharing_one_anchor_keep_original_order() -> None:
    raw = """# Title

Shared anchor paragraph with enough characters to survive the review.![A](assets/img_a.png)![B](assets/img_b.png)
"""
    reviewed = """# Title

Shared anchor paragraph with enough characters to survive the review.
"""

    restored = ensure_relevant_images_present(
        reviewed,
        {"assets/img_a.png", "assets/img_b.png"},
        raw_markdown=raw,
    )

    assert restored.index("assets/img_a.png") < restored.index("assets/img_b.png")


def test_image_whose_only_anchor_lives_inside_code_fence_is_appended() -> None:
    raw = """# Title

```
这是代码块里的内容，长度足够成为一个可用的锚点文本。
![X](assets/x.png)
```
"""
    reviewed = """# Title

```
这是代码块里的内容，长度足够成为一个可用的锚点文本。
```
"""

    restored = ensure_relevant_images_present(
        reviewed,
        {"assets/x.png"},
        raw_markdown=raw,
    )

    closing_fence = restored.index("```", restored.index("```") + 3)
    assert restored.index("assets/x.png") > closing_fence
