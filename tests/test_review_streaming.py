"""Prose-only review previews under arbitrary provider chunk boundaries."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from src.core.review.streaming import ReviewBodyStream, generate_review_text
from src.core.telemetry import emit_event, reset_event_sink, set_event_sink


@pytest.mark.parametrize("size", [1, 2, 7, 1000])
def test_json_preview_decodes_only_root_body_without_partial_escapes(size):
    body = '## 正文\n\n中文🙂e\u0301 "quote" \\ path\n\n[link](https://example.test)'
    raw = '```json\n' + json.dumps({"title": "Title", "metadata_candidates": {"markdown": "Hidden"},
                                   "markdown": body, "summary": "Internal context"}, ensure_ascii=True) + '\n```'
    parser = ReviewBodyStream()
    for index in range(0, len(raw), size):
        preview = parser.push(raw[index:index + size])
        assert body.startswith(preview)
        assert not any(0xD800 <= ord(char) <= 0xDFFF for char in preview)
    assert parser.text == body


def test_tag_preview_holds_partial_closing_tag_and_hides_summary():
    body = '## Part\n\nComplete prose.'
    raw = f'<reviewed_content>\n{body}</reviewed_content>\n<summary>Hidden</summary>'
    parser = ReviewBodyStream("tag")
    for char in raw:
        assert body.startswith(parser.push(char))
    assert parser.text == body


@pytest.mark.asyncio
async def test_review_call_transforms_deltas_and_restores_parent_consumer():
    events = []

    async def sink(*event):
        events.append(event)

    class Client:
        async def generate_text(self, *args):
            raw = json.dumps({"title": "Title", "markdown": "First\n\nSecond🙂", "summary": "Hidden"})
            for char in raw:
                await emit_event("ai_output_delta", "", char)
            await emit_event("ai_review", "progress")
            return SimpleNamespace(text=raw)

    token = set_event_sink(sink)
    try:
        await generate_review_text(Client(), "system", "user")
        assert events[-2] == ("review_output", "", "First\n\nSecond🙂")
        assert events[-1] == ("ai_review", "progress", None)
        assert not any(event[0] == "ai_output_delta" for event in events)
        await emit_event("ai_output_delta", "", "Parent restored")
        assert events[-1][2] == "Parent restored"
    finally:
        reset_event_sink(token)


@pytest.mark.asyncio
async def test_parallel_long_review_previews_keep_source_order_and_hide_synthesis(monkeypatch, tmp_path):
    from src.graph.tools import _review_long_article
    monkeypatch.setattr("src.core.paths.runtime_home", lambda: tmp_path)
    source = "# Title\n\n" + "First paragraph. " * 150 + "\n\n" + "Second paragraph. " * 150
    monkeypatch.setattr("src.graph.tools.bounded_chunks", lambda *args: ["First part.", "Second part."])
    events = []
    second_ready = asyncio.Event()

    async def sink(kind, message, details):
        if kind == "review_output":
            events.append(details)

    class Client:
        settings = SimpleNamespace(provider="test", model="test")

        async def generate_text(self, system, user):
            if "Article-level synthesis protocol" in system:
                await emit_event("ai_output_delta", "", '{"layout": "Hidden"}')
                return SimpleNamespace(text=json.dumps({"title": "Title", "summary": "Internal", "layout": [{"chunks": [1, 2]}]}))
            first = "part 1 of" in user
            if first:
                await second_ready.wait()
            raw = f'<reviewed_content>{"First part." if first else "Second part."}</reviewed_content><summary>Internal</summary>'
            for char in raw:
                await emit_event("ai_output_delta", "", char)
            if not first:
                assert events == [], "Later parts must not publish empty or out-of-order previews"
                second_ready.set()
            return SimpleNamespace(text=raw)

    token = set_event_sink(sink)
    try:
        payload, _ = await _review_long_article(client=Client(), system_prompt="Review", raw_markdown=source, image_filter_result=None)
    finally:
        reset_event_sink(token)
    assert payload.markdown == "First part.\n\nSecond part."
    assert all(payload.markdown.startswith(text) for text in events)
    assert events[-1] == payload.markdown
    assert all(events)
    assert all(before != after for before, after in zip(events, events[1:]))
