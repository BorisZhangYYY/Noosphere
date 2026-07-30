import json
from types import SimpleNamespace

import pytest

from src.graph.tools import (
    _parse_long_review_chunk_response,
    _preserve_chunk_images,
    _review_long_article,
)
from src.integrations.ai_client import AIOutputTruncatedError


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


def test_long_review_chunk_tag_protocol_accepts_unescaped_markdown() -> None:
    response = """<reviewed_content>
### Example

The user said "hello".

```python
print("not JSON escaped")
```
</reviewed_content>
<summary>
A quoted Python example.
</summary>"""

    content, summary, candidates = _parse_long_review_chunk_response(response)

    assert 'The user said "hello".' in content
    assert 'print("not JSON escaped")' in content
    assert summary == "A quoted Python example."
    assert candidates == {}


@pytest.mark.asyncio
async def test_long_review_chunk_protocol_collects_evidence_backed_metadata(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr("src.core.paths.runtime_home", lambda: tmp_path)

    class Client:
        settings = SimpleNamespace(provider="test", model="test-model")

        async def generate_text(self, system_prompt: str, user_prompt: str):
            assert "<metadata_candidates>" in system_prompt
            chunk = user_prompt.split("\n\n", 1)[-1]
            return SimpleNamespace(
                text=(
                    f"<reviewed_content>\n{chunk}\n</reviewed_content>\n"
                    "<summary>part</summary>\n"
                    '<metadata_candidates>{"author":{"value":"Ada",'
                    '"evidence":"Written by Ada"},"published_at":null}'
                    "</metadata_candidates>"
                ),
                provider="test",
                model="test-model",
            )

    payload, _ = await _review_long_article(
        client=Client(),
        system_prompt="Review faithfully.",
        raw_markdown="# Title\n\n---\n\nWritten by Ada\n\nA complete article body.",
        sections={"main_article": "Main Article"},
        body_section="main_article",
        image_filter_result=None,
    )

    assert payload.metadata_candidates["author"].value == "Ada"
    assert payload.metadata_candidates["author"].evidence == "Written by Ada"


@pytest.mark.asyncio
async def test_long_review_splits_when_provider_reports_token_truncation(
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
                raise AIOutputTruncatedError("test API output was truncated (max_tokens)")
            return SimpleNamespace(
                text=(
                    "<reviewed_content>\n"
                    + chunk
                    + "\n</reviewed_content>\n<summary>part</summary>"
                ),
                provider="test",
                model="test-model",
            )

    client = Client()
    source = "# Title\n\n---\n\n" + ("B" * 4700)
    payload, _ = await _review_long_article(
        client=client,
        system_prompt="Review faithfully.",
        raw_markdown=source,
        sections={"main_article": "Main Article"},
        body_section="main_article",
        image_filter_result=None,
    )

    assert max(client.chunk_sizes) > 3000
    assert len(client.chunk_sizes) >= 3
    assert "B" * 100 in payload.slots["main_article"]


@pytest.mark.asyncio
async def test_long_review_retries_invalid_article_synthesis(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr("src.core.paths.runtime_home", lambda: tmp_path)

    class Client:
        settings = SimpleNamespace(provider="test", model="test-model")

        def __init__(self) -> None:
            self.synthesis_calls = 0

        async def generate_text(self, system_prompt: str, user_prompt: str):
            if "Article-level synthesis protocol" in system_prompt:
                self.synthesis_calls += 1
                text = (
                    '{"title":"Title","slots":{"summary":"Complete summary"}}'
                    if self.synthesis_calls == 2
                    else '{"title":"Title","slots":{"summary":"unterminated'
                )
            else:
                chunk = user_prompt.split("\n\n", 1)[-1]
                text = (
                    "<reviewed_content>\n"
                    + chunk
                    + "\n</reviewed_content>\n<summary>part</summary>"
                )
            return SimpleNamespace(text=text, provider="test", model="test-model")

    client = Client()
    payload, _ = await _review_long_article(
        client=client,
        system_prompt="Review faithfully.",
        raw_markdown="# Title\n\n---\n\nA complete article body.",
        sections={"summary": "Summary", "main_article": "Main Article"},
        body_section="main_article",
        image_filter_result=None,
    )

    assert client.synthesis_calls == 2
    assert payload.slots["summary"] == "Complete summary"
