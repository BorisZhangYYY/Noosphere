import json
import re
from dataclasses import replace
from types import SimpleNamespace

import pytest

from src.graph.tools import (
    _assemble_long_review,
    _parse_long_review_chunk_response,
    _preserve_chunk_images,
    _review_long_article,
)
from src.integrations.ai_client import AIOutputTruncatedError


def synthesis_response(user_prompt: str, summary: str = "Summary") -> str:
    indexes = [int(index) for index in re.findall(r"^(\d+)\. ", user_prompt, flags=re.MULTILINE)]
    return json.dumps({
        "title": "Title", "summary": summary,
        "layout": [{"markdown": "## Full article", "chunks": indexes}],
    })


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
            if "Article-level synthesis protocol" in system_prompt:
                return SimpleNamespace(text=synthesis_response(user_prompt), provider="test", model="test-model")
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
        image_filter_result=None,
    )

    assert len(client.chunk_sizes) >= 3
    assert max(client.chunk_sizes) > 3000
    assert "A" * 100 in payload.markdown


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
                    text=synthesis_response(user_prompt),
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
        image_filter_result=None,
    )

    assert "A source paragraph that must never disappear." in payload.markdown
    assert payload.summary == "Summary"
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
            if "Article-level synthesis protocol" in system_prompt:
                return SimpleNamespace(text=synthesis_response(user_prompt), provider="test", model="test-model")
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
            if "Article-level synthesis protocol" in system_prompt:
                return SimpleNamespace(text=synthesis_response(user_prompt), provider="test", model="test-model")
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
        image_filter_result=None,
    )

    assert max(client.chunk_sizes) > 3000
    assert len(client.chunk_sizes) >= 3
    assert "B" * 100 in payload.markdown


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
                    synthesis_response(user_prompt, "Complete summary")
                    if self.synthesis_calls == 2
                    else '{"title":"Title","summary":"unterminated'
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
        image_filter_result=None,
    )

    assert client.synthesis_calls == 2
    assert payload.summary == "Complete summary"


def test_long_review_layout_keeps_full_parts_between_arbitrary_sections() -> None:
    payload = _assemble_long_review({
        "title": "Title", "summary": "Internal summary",
        "layout": [
            {"markdown": "## Background\n\nNecessary terms."},
            {"markdown": "---\n\n## Original reasoning", "chunks": [1, 2]},
            {"markdown": "## Limitations\n\nClosing guidance."},
        ],
    }, ["## Original section\n\nComplete first part.", "Complete second part."])
    assert "## Original section" in payload.markdown
    assert payload.markdown.index("Complete first part.") < payload.markdown.index("Complete second part.")
    assert payload.markdown.endswith("Closing guidance.")
    assert "Internal summary" not in payload.markdown


@pytest.mark.parametrize("indexes", [[1], [1, 1, 2], [1, 3], [True, 2], ["1", 2]])
def test_long_review_layout_rejects_missing_duplicate_or_invalid_parts(indexes) -> None:
    with pytest.raises(ValueError, match="part"):
        _assemble_long_review({
            "title": "Title", "summary": "Summary", "layout": [{"chunks": indexes}],
        }, ["First part", "Second part"])


@pytest.mark.asyncio
async def test_below_threshold_output_truncation_recovers_using_bounded_review(monkeypatch):
    from src.graph.tools import edit_article, LONG_REVIEW_THRESHOLD
    from src.integrations.ai_client import AIClient, AITextResponse
    from src.core.telemetry import set_event_sink, reset_event_sink
    from src.integrations.model_limits import ModelLimits

    async def sufficient_budget(self):
        self.settings = replace(self.settings, max_output_tokens=24000)
        return ModelLimits()

    monkeypatch.setattr(AIClient, 'prepare_limits', sufficient_budget)

    source_body = 'Evidence and complete reasoning must survive.\n\n' * 240
    source = '# Source\n\n> Source: [https://example.com](https://example.com)\n\n---\n\n' + source_body
    assert len(source) < LONG_REVIEW_THRESHOLD
    calls = []
    events = []

    async def generate(self, system_prompt, user_prompt):
        calls.append((system_prompt, user_prompt))
        if '# Response protocol' in system_prompt:
            raise AIOutputTruncatedError('test API output was truncated (length)')
        if 'Article-level synthesis protocol' in system_prompt:
            return AITextResponse(text=synthesis_response(user_prompt), model='test-model', provider='test')
        assert 'Long article chunk protocol' in system_prompt
        chunk = user_prompt.split('\n\n', 1)[1]
        return AITextResponse(text=json.dumps({'content': chunk, 'summary': 'Preserved evidence'}), model='test-model', provider='test')

    async def event_sink(kind, message, details):
        events.append(message)

    monkeypatch.setattr(AIClient, 'generate_text', generate)
    token = set_event_sink(event_sink)
    try:
        result = await edit_article.ainvoke({'raw_markdown': source, 'feedback': '', 'platform': 'web',
                                            'content_type': 'article', 'perspective': 'original', 'output_language': 'en-US'})
    finally:
        reset_event_sink(token)
    assert 'pipeline.events.aiReviewTruncatedFallback' in events
    assert sum('# Response protocol' in system for system, _ in calls) == 1
    assert sum('Long article chunk protocol' in system for system, _ in calls) >= 2
    assert result['markdown'].count('Evidence and complete reasoning must survive.') == 240
    assert result['summary'] == 'Summary'
    assert '> Source: [https://example.com](https://example.com)' in result['markdown']


@pytest.mark.asyncio
async def test_review_routes_to_chunks_before_any_oversized_generation(monkeypatch):
    from src.graph.tools import edit_article
    from src.integrations.ai_client import AIClient, AITextResponse
    from src.core.telemetry import set_event_sink, reset_event_sink

    source = '# Source\n\n---\n\n' + ('完整保留每一条事实和论证。\n\n' * 300)
    calls, events = [], []

    async def generate(self, system_prompt, user_prompt):
        calls.append(system_prompt)
        assert '# Response protocol' not in system_prompt
        if 'Article-level synthesis protocol' in system_prompt:
            text = synthesis_response(user_prompt)
        else:
            chunk = user_prompt.split('\n\n', 1)[1]
            assert len(chunk.encode('utf-8')) <= 5317
            text = json.dumps({'content': chunk, 'summary': '完整事实'})
        return AITextResponse(text=text, model='test-model', provider='test')

    async def sink(kind, message, details):
        events.append(message)

    monkeypatch.setattr(AIClient, 'generate_text', generate)
    token = set_event_sink(sink)
    try:
        result = await edit_article.ainvoke({'raw_markdown': source, 'feedback': '', 'platform': 'web',
                                            'content_type': 'article', 'perspective': 'original', 'output_language': 'zh-CN'})
    finally:
        reset_event_sink(token)
    assert events[0] == 'pipeline.events.aiReviewPreflightSplit'
    assert len(calls) >= 3
    assert result['markdown'].count('完整保留每一条事实和论证。') == 300


@pytest.mark.asyncio
async def test_review_rejects_impossible_prompt_budget_without_generating(monkeypatch):
    from src.graph.tools import edit_article
    from src.integrations.ai_client import AIClient
    from src.integrations.model_limits import ModelLimits

    async def tiny_context(self):
        self.model_limits = ModelLimits(context_tokens=1500, output_tokens=1000)
        return self.model_limits

    async def never_generate(*args, **kwargs):
        pytest.fail('An impossible prompt must be rejected before generation')

    monkeypatch.setattr(AIClient, 'prepare_limits', tiny_context)
    monkeypatch.setattr(AIClient, 'generate_text', never_generate)
    with pytest.raises(ValueError, match='No generation request was sent'):
        await edit_article.ainvoke({'raw_markdown': '# Title\n\n---\n\nBody', 'feedback': '', 'platform': 'web',
                                    'content_type': 'article', 'perspective': 'original', 'output_language': 'en-US'})


@pytest.mark.asyncio
async def test_known_large_capacity_uses_one_call_instead_of_fixed_character_trigger(monkeypatch):
    from src.graph.tools import edit_article
    from src.integrations.ai_client import AIClient, AITextResponse
    from src.integrations.model_limits import ModelLimits

    body = 'Complete source reasoning. ' * 800
    assert len(body) > 18000
    calls = []

    async def large_capacity(self):
        self.settings = replace(self.settings, max_output_tokens=131072)
        self.model_limits = ModelLimits(context_tokens=1048576, output_tokens=393216)
        return self.model_limits

    async def generate(self, system_prompt, user_prompt):
        calls.append(user_prompt)
        assert '# Response protocol' in system_prompt
        return AITextResponse(text=json.dumps({'title': 'Title', 'markdown': body, 'summary': 'Summary'}),
                              model='test-model', provider='test')

    monkeypatch.setattr(AIClient, 'prepare_limits', large_capacity)
    monkeypatch.setattr(AIClient, 'generate_text', generate)
    result = await edit_article.ainvoke({'raw_markdown': '# Title\n\n---\n\n' + body, 'feedback': '', 'platform': 'web',
                                        'content_type': 'article', 'perspective': 'original', 'output_language': 'en-US'})
    assert len(calls) == 1
    assert result['markdown'].count('Complete source reasoning.') == 800
