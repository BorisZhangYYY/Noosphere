import json
from types import SimpleNamespace

import pytest

from src.graph.tools import _preserve_chunk_images, _review_long_article


@pytest.mark.asyncio
async def test_long_review_splits_a_chunk_when_provider_returns_empty_content(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr("src.core.paths.runtime_home", lambda: tmp_path)

    class Client:
        settings = SimpleNamespace(provider="test", model="test-model")

        def __init__(self) -> None:
            self.chunk_sizes: list[int] = []

        async def generate_text(self, system_prompt: str, user_prompt: str):
            chunk = user_prompt.split("\n\n", 1)[-1]
            self.chunk_sizes.append(len(chunk))
            if len(chunk) > 3000:
                text = json.dumps({"content": "", "summary": ""})
            else:
                text = json.dumps({"content": chunk, "summary": "part"})
            return SimpleNamespace(text=text, provider="test", model="test-model")

    client = Client()
    source = "# Title\n\n> Source: [https://example.com](https://example.com)\n\n---\n\n" + ("A" * 4700)

    payload, _ = await _review_long_article(
        client=client,
        system_prompt="Review faithfully.",
        raw_markdown=source,
        sections={"main_article": "Main Article"},
        body_section="main_article",
        image_filter_result=None,
    )

    assert len(client.chunk_sizes) >= 3
    assert max(client.chunk_sizes) > 3000
    assert "A" * 100 in payload.slots["main_article"]


@pytest.mark.asyncio
async def test_long_review_retains_source_when_provider_never_returns_content(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr("src.core.paths.runtime_home", lambda: tmp_path)

    class Client:
        settings = SimpleNamespace(provider="test", model="test-model")

        async def generate_text(self, system_prompt: str, user_prompt: str):
            if "Article-level synthesis protocol" in system_prompt:
                return SimpleNamespace(
                    text=json.dumps({"title": "Title", "slots": {"summary": "Summary"}}),
                    provider="test",
                    model="test-model",
                )
            return SimpleNamespace(
                text=json.dumps({"content": "", "summary": ""}),
                provider="test",
                model="test-model",
            )

    source_text = "A source paragraph that must never disappear. " * 130
    payload, response = await _review_long_article(
        client=Client(),
        system_prompt="Review faithfully.",
        raw_markdown="# Title\n\n---\n\n" + source_text,
        sections={"summary": "Summary", "main_article": "Main Article"},
        body_section="main_article",
        image_filter_result=None,
    )

    assert "A source paragraph that must never disappear." in payload.slots["main_article"]
    assert payload.slots["summary"] == "Summary"
    assert response.model == "test-model"


def test_long_review_rejects_fabricated_and_duplicate_image_paths() -> None:
    source = "Before\n\n![one](assets/image_01_abcdef.png)\n\nAfter"
    reviewed = (
        "Before\n\n![one](assets/image_01_abcdef.png)\n\n"
        "![duplicate](assets/image_01_abcdef.png)\n\n"
        "![typo](assets/image_01_abcedf.png)\n\nAfter"
    )

    preserved = _preserve_chunk_images(reviewed, source)

    assert preserved.count("assets/image_01_abcdef.png") == 1
    assert "assets/image_01_abcedf.png" not in preserved
