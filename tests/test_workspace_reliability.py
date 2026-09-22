"""Failure and concurrency regressions for the workspace reliability release."""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from starlette.testclient import TestClient

from test_web_api import web_client
from src.api import web
from src.application import service
from src.core.content import ArticleContentStore, recover_missing_article_workspaces, retry_mirror
from src.core.jobs import JobStore
from src.core.workspace import RevisionConflict, content_revision
from src.mcp.server import create_app


def test_existing_content_table_upgrades_without_losing_original_text():
    store = ArticleContentStore()
    with store._connect() as connection:
        connection.execute("CREATE TABLE noosphere_article_content (article_id TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '', source_url TEXT NOT NULL DEFAULT '', raw_markdown TEXT NOT NULL DEFAULT '', reviewed_markdown TEXT NOT NULL DEFAULT '', reflection_markdown TEXT NOT NULL DEFAULT '', annotations_json TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL)")
        connection.execute("INSERT INTO noosphere_article_content (article_id, raw_markdown, updated_at) VALUES ('legacy', 'Original text', '2026-09-18')")
    store.ensure_schema()
    store.upsert_content("legacy", manifest_json='{"article_id":"legacy"}', present_files_json='["raw.md"]')
    content = store.get_content("legacy")
    assert content["raw_markdown"] == "Original text"
    assert content["manifest_json"] == '{"article_id":"legacy"}'


def test_forged_host_and_forwarded_peer_never_grant_network_access(web_client, monkeypatch):
    _, _, article_id = web_client
    client = TestClient(create_app(), client=("198.51.100.23", 42000))
    headers = {"host": "localhost:8080", "x-forwarded-for": "127.0.0.1"}
    for path in ("/api/v1/settings", f"/api/v1/articles/{article_id}", "/sse", "/app/"):
        assert client.get(path, headers=headers).status_code == 403
    assert client.post("/api/v1/settings/secrets/reveal", headers=headers, json={"service": "ai"}).status_code == 403
    monkeypatch.setenv("NOOSPHERE_ACCESS_TOKEN", "fake-access-token")
    assert client.get("/api/v1/settings", headers=headers).status_code == 401
    assert client.get("/api/v1/settings", headers={**headers, "authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/v1/settings", headers={**headers, "authorization": "Bearer fake-access-token"}).status_code == 200
    assert client.get("/api/v1/settings", headers=headers, auth=("noosphere", "fake-access-token")).status_code == 200
    assert client.get("/health").status_code == 200


def test_authenticated_browser_rejects_cross_origin_write(web_client, monkeypatch):
    client, _, _ = web_client
    monkeypatch.setenv("NOOSPHERE_ACCESS_TOKEN", "fake-access-token")
    response = client.patch("/api/v1/settings", headers={"authorization": "Bearer fake-access-token", "origin": "https://untrusted.example"}, json={})
    assert response.status_code == 403


def test_stale_web_save_and_mcp_save_are_rejected(web_client):
    client, _, article_id = web_client
    detail = client.get(f"/api/v1/articles/{article_id}").json()
    saved = client.patch(f"/api/v1/articles/{article_id}", json={"reviewedMarkdown": "# First change\n", "expectedRevision": detail["revision"]})
    assert saved.status_code == 200
    stale = client.patch(f"/api/v1/articles/{article_id}", json={"reviewedMarkdown": "# Stale change\n", "expectedRevision": detail["revision"]})
    assert stale.status_code == 409
    from src.mcp.server import update_article_content
    with pytest.raises(RevisionConflict):
        asyncio.run(update_article_content(article_id, "# Also stale\n", expected_revision=detail["revision"]))
    assert client.get(f"/api/v1/articles/{article_id}").json()["title"] == "First change"


def test_simultaneous_writers_have_exactly_one_winner(web_client):
    _, _, article_id = web_client
    revision = service.get_article(article_id)["revision"]
    def save(title):
        try:
            service.save_reviewed_markdown(article_id, f"# {title}\n", expected_revision=revision)
            return "saved"
        except RevisionConflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save, ["one", "two"])) == ["conflict", "saved"]


def test_permanent_delete_failure_cannot_resurrect_and_can_retry(web_client, monkeypatch):
    client, config_path, article_id = web_client
    output = config_path.parent / "articles"
    assert retry_mirror(article_id)["status"] == "synced"
    service.trash_articles([article_id])
    with monkeypatch.context() as patch:
        patch.setattr(ArticleContentStore, "delete_content", lambda *args: (_ for _ in ()).throw(OSError("simulated failure")))
        with pytest.raises(OSError):
            service.permanently_delete_trashed_articles([article_id])
    assert ArticleContentStore().is_deleted(article_id)
    assert recover_missing_article_workspaces(output) == 0
    assert client.get(f"/api/v1/articles/{article_id}").status_code == 404
    assert any(row["id"] == article_id for row in service.list_trashed_articles())
    assert service.permanently_delete_trashed_articles([article_id]) == [article_id]
    assert ArticleContentStore().get_content(article_id) is None


@pytest.mark.parametrize("name", ["raw.md", "reviewed.md", "reflection.md", "annotations.json", "manifest.json", "review.json"])
def test_partial_file_loss_recovers_exact_content(web_client, name):
    client, config_path, article_id = web_client
    directory = config_path.parent / "articles" / article_id
    (directory / "reflection.md").write_text("")
    (directory / "annotations.json").write_text(json.dumps({"version": 1, "annotations": []}))
    if not (directory / "review.json").exists():
        (directory / "review.json").write_text('{"status":"reviewed"}')
    before = (directory / name).read_bytes()
    assert retry_mirror(article_id)["status"] == "synced"
    (directory / name).unlink()
    response = client.get(f"/api/v1/articles/{article_id}")
    assert response.status_code == 200
    assert (directory / name).read_bytes() == before


def test_existing_empty_file_is_not_replaced_from_backup(web_client):
    client, config_path, article_id = web_client
    directory = config_path.parent / "articles" / article_id
    retry_mirror(article_id)
    (directory / "reviewed.md").write_text("")
    client.get(f"/api/v1/articles/{article_id}")
    assert (directory / "reviewed.md").read_text() == ""


def test_failed_mirror_is_visible_and_retryable(web_client, monkeypatch):
    client, _, article_id = web_client
    with monkeypatch.context() as patch:
        patch.setattr(ArticleContentStore, "upsert_content", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("simulated failure")))
        service.save_reviewed_markdown(article_id, "# Saved despite mirror failure\n")
    detail = client.get(f"/api/v1/articles/{article_id}").json()
    assert detail["mirrorStatus"]["status"] == "failed"
    assert detail["title"] == "Saved despite mirror failure"
    assert client.post(f"/api/v1/articles/{article_id}/mirror/retry").json()["status"] == "synced"


def test_restart_recovers_jobs_as_interrupted_without_replaying_uploads(web_client):
    store = JobStore()
    store.save({"id": "old-upload", "kind": "upload", "status": "running", "articleId": "test"})
    store.save({"id": "completed", "kind": "review", "status": "succeeded"})
    web.recover_background_jobs()
    assert web.get_background_job("old-upload")["status"] == "failed"
    assert web.get_background_job("old-upload")["interrupted"] is True
    assert web.get_background_job("completed")["status"] == "succeeded"
    assert next(job for job in store.list() if job["id"] == "old-upload")["status"] == "failed"


def test_retention_does_not_evict_active_jobs(web_client):
    group = {"active": {"status": "running"}}
    group.update({str(i): {"status": "succeeded"} for i in range(130)})
    web._prune_completed_jobs(group)
    assert "active" in group
    assert len(group) == 101


@pytest.mark.asyncio
async def test_queue_limits_execution_and_persists_completion(web_client, monkeypatch):
    monkeypatch.setenv("NOOSPHERE_JOB_CONCURRENCY", "1")
    started = []
    release = asyncio.Event()
    async def runner(job_id):
        started.append(job_id)
        web._review_jobs[job_id]["status"] = "running"
        await release.wait()
        web._review_jobs[job_id]["status"] = "succeeded"
    for index in range(3):
        job_id = f"queue-{index}"
        web._review_jobs[job_id] = {"id": job_id, "kind": "review", "status": "queued"}
        web._queue_job(web._review_jobs, job_id, runner)
    await asyncio.sleep(0.03)
    assert len(started) == 1
    assert len(JobStore().list()) == 3
    release.set()
    await asyncio.gather(*list(web._background_tasks))
    assert len(started) == 3
    assert all(job["status"] == "succeeded" for job in JobStore().list())


def test_list_pagination_and_cache_invalidate_after_edit(web_client):
    client, _, article_id = web_client
    assert client.get("/api/v1/articles?limit=1&offset=1").json()["articles"] == []
    assert client.get("/api/v1/articles?limit=no").status_code == 400
    client.get("/api/v1/articles")
    service.save_reviewed_markdown(article_id, "# Updated title\n")
    assert client.get("/api/v1/articles").json()["articles"][0]["title"] == "Updated title"


def test_http_content_updates_require_a_revision(web_client):
    client, _, article_id = web_client
    assert client.patch(f"/api/v1/articles/{article_id}", json={"reviewedMarkdown": "# Unversioned write"}).status_code == 428


@pytest.mark.asyncio
async def test_ai_review_does_not_overwrite_edits_made_while_model_is_running(web_client, monkeypatch):
    _, config_path, article_id = web_client
    from src.graph.graph import _edit_node
    from src.graph import graph
    directory = config_path.parent / "articles" / article_id
    before_raw = (directory / "raw.md").read_bytes()
    class FakeEditor:
        async def ainvoke(self, payload):
            service.save_reviewed_markdown(article_id, "# Written during model request\n")
            return {"markdown": "# Stale AI response\n"}
    monkeypatch.setattr(graph, "edit_article", FakeEditor())
    state = {"article_id": article_id, "reviewed_path": str(directory / "reviewed.md"), "raw_markdown": "# Input", "platform": "wechat_mp", "content_type": "article"}
    with pytest.raises(RevisionConflict):
        await _edit_node(state)
    assert "Written during model request" in (directory / "reviewed.md").read_text()
    assert (directory / "raw.md").read_bytes() == before_raw


def test_reflection_preference_does_not_conflict_with_body_draft(web_client):
    _, _, article_id = web_client
    before = service.get_article(article_id)["revision"]
    service.save_reflection(article_id, markdown="My note", upload_enabled=True)
    assert service.get_article(article_id)["revision"] == before
    assert service.save_reviewed_markdown(article_id, "# My draft", expected_revision=before)["ok"]


@pytest.mark.parametrize("value", ["invalid", "0", "-1", "101"])
def test_invalid_concurrency_is_rejected_before_queuing(web_client, monkeypatch, value):
    monkeypatch.setenv("NOOSPHERE_JOB_CONCURRENCY", value)
    with pytest.raises(ValueError, match="JOB_CONCURRENCY"):
        web._check_job_capacity()
