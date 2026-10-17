"""Live job snapshots, reconnection and review-output preservation."""
import json
from types import SimpleNamespace

import pytest

from src.api.web import _background_job_events, _capture_jobs, _review_jobs, _run_capture_job
from test_web_api import web_client


class ConnectedRequest:
    async def is_disconnected(self):
        return False


def payload(event):
    assert event.startswith("event: jobs\ndata: ")
    return json.loads(event.split("data: ", 1)[1])


@pytest.mark.asyncio
async def test_job_stream_updates_removes_and_resets_on_reconnection(web_client):
    _, _, article_id = web_client
    stream = _background_job_events(ConnectedRequest(), "all")
    assert payload(await anext(stream)) == {"reset": True, "jobs": [], "removedIds": []}
    job = {"id": "live-review", "kind": "review", "articleId": article_id,
           "status": "running", "createdAt": "2026-10-15", "reviewPreview": "First paragraph"}
    _review_jobs[job["id"]] = job
    update = payload(await anext(stream))
    assert update["reset"] is False
    assert update["jobs"][0]["reviewPreview"] == "First paragraph"
    job["reviewPreview"] += "\n\nSecond paragraph"
    assert payload(await anext(stream))["jobs"][0]["reviewPreview"].endswith("Second paragraph")
    job["status"] = "succeeded"
    assert payload(await anext(stream))["jobs"][0]["status"] == "succeeded"
    reconnect = _background_job_events(ConnectedRequest(), "review")
    snapshot = payload(await anext(reconnect))
    assert snapshot["reset"] is True
    assert snapshot["jobs"][0]["reviewPreview"] == job["reviewPreview"]
    await reconnect.aclose()
    _review_jobs.clear()
    assert payload(await anext(stream))["removedIds"] == ["live-review"]
    await stream.aclose()


def test_job_stream_validates_kind_before_streaming(web_client):
    client, _, _ = web_client
    response = client.get("/api/v1/jobs/stream?kind=unknown")
    assert response.status_code == 400
    assert "kind must be one of" in response.json()["error"]


def test_job_stream_uses_existing_authentication_and_origin_checks(web_client, monkeypatch):
    client, _, _ = web_client
    monkeypatch.setenv("NOOSPHERE_ACCESS_TOKEN", "stream-test-token")
    assert client.get("/api/v1/jobs/stream").status_code == 401
    response = client.get("/api/v1/jobs/stream", headers={
        "Authorization": "Bearer stream-test-token", "Origin": "https://other.example",
    })
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_capture_stream_discards_truncated_attempt_but_retains_complete_output(web_client, monkeypatch):
    from src.core.telemetry import emit_event

    _, config, article_id = web_client
    path = config.parent / "articles" / article_id / "reviewed.md"
    _capture_jobs["capture-stream"] = {"id": "capture-stream", "events": [], "reviewPreview": ""}
    complete = "First paragraph.\n" + "完整审阅内容" * 6000

    async def extract(url):
        return path

    async def review(path, **kwargs):
        await emit_event("review_output", "", "Discard this partial attempt")
        await emit_event("ai_review", "pipeline.events.aiReviewTruncatedFallback")
        assert _capture_jobs["capture-stream"]["reviewPreview"] == ""
        await emit_event("review_output", "", complete[:18000])
        await emit_event("review_output", "", complete)
        await emit_event("ai_output_delta", "", '{"internal": "not article text"}')
        path.write_text(complete)
        return SimpleNamespace(ok=True, issues=[])

    async def place(*args):
        return {"collection_id": None}

    monkeypatch.setattr("src.graph.graph.run_extract_graph", extract)
    monkeypatch.setattr("src.graph.graph.run_ai_review_graph", review)
    monkeypatch.setattr("src.core.collections.place_reviewed_article", place)
    await _run_capture_job("capture-stream", "https://example.test/article", "ai_then_manual", "original", "source")
    assert _capture_jobs["capture-stream"]["status"] == "awaiting_review"
    assert _capture_jobs["capture-stream"]["reviewPreview"] == complete
