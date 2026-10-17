"""Cancellable reviews publish complete results without touching the starting article."""
import asyncio
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_web_api import web_client, _create_collection_path
from src.core.activity import ArticleActivityStore
from src.core.collections import CollectionStore
from src.core.content import ArticleContentStore, mirror_content
from src.core.review.image_layout import ImageLayout
from src.core.telemetry import emit_event
from src.core.workspace import atomic_write_text, content_revision


def wait_for_job(client, job_id, predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if predicate(job):
            return job
        time.sleep(0.01)
    raise AssertionError(job)


def snapshot(directory):
    return {str(path.relative_to(directory)): path.read_bytes() for path in directory.rglob("*") if path.is_file()}


def install_review(monkeypatch, article_id, entered, release, phase="text"):
    async def review(path, **kwargs):
        from src.core.review.transaction import joined_worker
        from src.graph.graph import _commit_image_layout, _commit_review

        await emit_event("review_output", "", "# Live preview\n\nHalf of a new article.")
        state = {"article_id": article_id, "reviewed_path": str(path), "assets_dir": str(path.parent / "assets"),
                 "raw_markdown": kwargs["source_markdown"], "review_perspective": "original", "output_language": "en-US"}
        completed = await joined_worker(_commit_review, article_id, state,
                                        {"markdown": "# Finished review\n\nComplete prose.\n", "summary": "Summary", "model": "test", "provider": "fake"},
                                        1, content_revision(path.parent))
        state.update(completed)
        await joined_worker(_commit_image_layout, article_id, state,
                            ImageLayout("# Finished review\n\nComplete prose.\n", {"assets/image.png"}, [], []),
                            {"status": "completed"}, {"assets/image.png"})
        if phase == "text":
            entered.set()
            while not release.is_set():
                await asyncio.sleep(0.01)
        return SimpleNamespace(ok=True, issues=[])

    async def place(placed_id, path, locale):
        assignment = CollectionStore().assign_article(placed_id, collection_id=None, source="ai", confidence=0, reason="No match")
        if phase == "classification":
            entered.set()
            while not release.is_set():
                await asyncio.sleep(0.01)
        return assignment

    monkeypatch.setattr("src.graph.graph.run_ai_review_graph", review)
    monkeypatch.setattr("src.core.collections.place_reviewed_article", place)


@pytest.mark.parametrize("kind", ["review", "capture"])
@pytest.mark.parametrize("phase", ["text", "classification"])
def test_cancel_discards_partial_prose_images_metadata_counts_and_classification(web_client, monkeypatch, kind, phase):
    client, config, article_id = web_client
    directory = config.parent / "articles" / article_id
    original_collection, _ = _create_collection_path(client, "Original collection")
    CollectionStore().assign_article(article_id, collection_id=original_collection)
    ArticleActivityStore().record(article_id, "review", model="starting")
    (directory / "review.json").write_text(json.dumps({"status": "reviewed", "summary": "Original summary"}))
    (directory / "reflection.md").write_text("Private reflection")
    before_detail = client.get(f"/api/v1/articles/{article_id}").json()
    before = snapshot(directory)
    mirror_content(article_id, reviewed_markdown=(directory / "reviewed.md").read_text())
    before_mirror = ArticleContentStore().get_content(article_id)
    entered, release = threading.Event(), threading.Event()
    install_review(monkeypatch, article_id, entered, release, phase)
    if kind == "capture":
        async def extract(url):
            return directory / "reviewed.md"
        monkeypatch.setattr("src.graph.graph.run_extract_graph", extract)
        response = client.post("/api/v1/captures", json={"url": "https://example.com/cancellable", "reviewMode": "ai_then_manual"})
    else:
        response = client.post(f"/api/v1/articles/{article_id}/review", json={})
    assert response.status_code == 202
    job_id = response.json()["id"]
    assert entered.wait(5)
    active = client.get(f"/api/v1/articles/{article_id}").json()
    assert active["activeReview"]["id"] == job_id
    assert snapshot(directory) == before
    assert ArticleContentStore().get_content(article_id) == before_mirror
    assert active["operationSummary"]["reviewCount"] == before_detail["operationSummary"]["reviewCount"]
    assert CollectionStore().get_assignment(article_id)["collection_id"] == original_collection
    cancelled = client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["reviewPreview"] == ""
    release.set()
    after = client.get(f"/api/v1/articles/{article_id}").json()
    assert snapshot(directory) == before
    assert after["activeReview"] is None
    assert after["operationSummary"]["reviewCount"] == before_detail["operationSummary"]["reviewCount"]
    assert after["revision"] == before_detail["revision"]
    assert after["collection"] == before_detail["collection"]
    assert client.post(f"/api/v1/jobs/{job_id}/cancel").status_code == 200
    assert not list((config.parent / "pending-reviews").glob("*"))


def test_success_publishes_complete_review_and_preserves_private_sidecars(web_client, monkeypatch):
    client, config, article_id = web_client
    directory = config.parent / "articles" / article_id
    before = client.get(f"/api/v1/articles/{article_id}").json()
    raw = (directory / "raw.md").read_bytes()
    entered, release = threading.Event(), threading.Event()
    install_review(monkeypatch, article_id, entered, release, "classification")
    job = client.post(f"/api/v1/articles/{article_id}/review", json={}).json()
    assert entered.wait(5)
    (directory / "reflection.md").write_text("New private reflection")
    (directory / "annotations.json").write_text('{"version": 1, "annotations": []}')
    manifest = json.loads((directory / "manifest.json").read_text())
    manifest["reflection"] = {"upload_enabled": True}
    atomic_write_text(directory / "manifest.json", json.dumps(manifest))
    release.set()
    result = wait_for_job(client, job["id"], lambda item: item["status"] not in {"queued", "running"})
    assert result["status"] == "succeeded", result
    assert (directory / "reviewed.md").read_text() == "# Finished review\n\nComplete prose.\n"
    assert (directory / "removed/image.png").is_file()
    assert not (directory / "assets/image.png").exists()
    assert (directory / "raw.md").read_bytes() == raw
    assert (directory / "reflection.md").read_text() == "New private reflection"
    assert json.loads((directory / "manifest.json").read_text())["reflection"]["upload_enabled"]
    after = client.get(f"/api/v1/articles/{article_id}").json()
    assert after["operationSummary"]["reviewCount"] == before["operationSummary"]["reviewCount"] + 1
    assert after["revision"] == result["reviewRevision"]
    assert client.post(f"/api/v1/jobs/{job['id']}/cancel").status_code == 409
    assert not list((config.parent / "pending-reviews").glob("*"))


def test_concurrent_saved_edit_is_never_overwritten_by_review(web_client, monkeypatch):
    client, config, article_id = web_client
    directory = config.parent / "articles" / article_id
    entered, release = threading.Event(), threading.Event()
    install_review(monkeypatch, article_id, entered, release)
    job = client.post(f"/api/v1/articles/{article_id}/review", json={}).json()
    assert entered.wait(5)
    atomic_write_text(directory / "reviewed.md", "# Saved in another window\n")
    release.set()
    result = wait_for_job(client, job["id"], lambda item: item["status"] not in {"queued", "running"})
    assert result["status"] == "failed"
    assert "Article changed" in result["error"]
    assert (directory / "reviewed.md").read_text() == "# Saved in another window\n"
    assert (directory / "assets/image.png").exists()
    assert not (directory / "removed/image.png").exists()


def test_queued_review_can_cancel_without_starting_provider(web_client, monkeypatch):
    from src.api.web import _job_semaphores
    client, config, article_id = web_client
    monkeypatch.setenv("NOOSPHERE_JOB_CONCURRENCY", "1")
    _job_semaphores.clear()
    entered = threading.Event()
    calls = []
    async def blocking_extract(url):
        entered.set()
        await asyncio.Event().wait()
    async def review(*args, **kwargs):
        calls.append(args)
        raise AssertionError("Cancelled queued review must not reach the provider")
    monkeypatch.setattr("src.graph.graph.run_extract_graph", blocking_extract)
    monkeypatch.setattr("src.graph.graph.run_ai_review_graph", review)
    client.post("/api/v1/captures", json={"url": "https://example.com/blocker"})
    assert entered.wait(5)
    queued = client.post(f"/api/v1/articles/{article_id}/review", json={}).json()
    assert queued["status"] == "queued"
    cancelled = client.post(f"/api/v1/jobs/{queued['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert not calls


def test_cancellation_joins_inflight_disk_writer_before_discarding_stage(web_client, monkeypatch):
    from src.core.review.transaction import joined_worker
    client, config, article_id = web_client
    directory = config.parent / "articles" / article_id
    client.get(f"/api/v1/articles/{article_id}")
    before = snapshot(directory)
    entered, release = threading.Event(), threading.Event()
    async def review(path, **kwargs):
        def writer():
            entered.set()
            assert release.wait(5)
            atomic_write_text(path, "# Late staged write\n")
        await joined_worker(writer)
        return SimpleNamespace(ok=True, issues=[])
    monkeypatch.setattr("src.graph.graph.run_ai_review_graph", review)
    job = client.post(f"/api/v1/articles/{article_id}/review", json={}).json()
    assert entered.wait(5)
    responses = []
    cancellation = threading.Thread(target=lambda: responses.append(client.post(f"/api/v1/jobs/{job['id']}/cancel")))
    cancellation.start()
    wait_for_job(client, job["id"], lambda item: item.get("cancelRequested"))
    assert cancellation.is_alive()
    release.set()
    cancellation.join(5)
    assert responses[0].json()["status"] == "cancelled"
    assert snapshot(directory) == before
    assert not list((config.parent / "pending-reviews").glob("*"))


def test_cancelled_state_survives_a_delayed_older_job_snapshot(web_client, monkeypatch):
    from src.core.jobs import JobStore
    client, _, article_id = web_client
    entered, release = threading.Event(), threading.Event()
    save = JobStore.save
    def delayed_save(self, job):
        if job["kind"] == "review" and job["status"] == "running" and not entered.is_set():
            entered.set()
            assert release.wait(5)
        save(self, job)
    async def review(path, **kwargs):
        await emit_event("review_output", "", "Half written preview")
        await asyncio.Event().wait()
    monkeypatch.setattr(JobStore, "save", delayed_save)
    monkeypatch.setattr("src.graph.graph.run_ai_review_graph", review)
    job = client.post(f"/api/v1/articles/{article_id}/review", json={}).json()
    assert entered.wait(5)
    responses = []
    cancellation = threading.Thread(target=lambda: responses.append(client.post(f"/api/v1/jobs/{job['id']}/cancel")))
    cancellation.start()
    wait_for_job(client, job["id"], lambda item: item.get("cancelRequested"))
    release.set()
    cancellation.join(5)
    assert responses[0].json()["status"] == "cancelled"
    saved = next(item for item in JobStore().list() if item["id"] == job["id"])
    assert saved["status"] == "cancelled"
    assert saved["reviewPreview"] == ""
