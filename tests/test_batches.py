"""Batch state-machine tests without real crawler/model calls."""
import asyncio
import json
from pathlib import Path

import pytest
from test_web_api import web_client
from src.api import web
from src.application import batches
from src.core.jobs import JobStore


async def drain():
    await asyncio.gather(*list(web._background_tasks))


def fake_capture(config, calls):
    async def capture(url):
        calls.append(url)
        folder = config.parent / 'articles' / f'captured_{len(calls)}'
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'manifest.json').write_text(json.dumps({'article_id': folder.name, 'article': {'title': 'Captured', 'url': url}, 'paths': {'raw': 'raw.md', 'reviewed': 'reviewed.md'}}))
        (folder / 'raw.md').write_text('# Captured\n\nOriginal text')
        (folder / 'reviewed.md').write_text('# Captured\n\nOriginal text')
        return folder / 'reviewed.md'
    return capture


def test_preflight_normalizes_fragments_and_preserves_queries(web_client):
    result = batches.preflight(['https://EXAMPLE.com/a#one', 'https://example.com/a#two', 'https://example.com/a?id=2', 'not-url', 'https://mp.weixin.qq.com/s/example'])
    assert [i['status'] for i in result] == ['pending', 'skipped', 'pending', 'invalid', 'skipped']
    assert result[1]['reason'] == 'duplicate'
    assert result[4]['reason'] == 'existing'
    with pytest.raises(ValueError):
        batches.preflight(['https://example.com'] * 101)


@pytest.mark.asyncio
async def test_completed_capture_is_not_repeated_after_review_retry(web_client, monkeypatch):
    _, config, _ = web_client
    from src.graph import graph
    captures, reviews = [], []
    monkeypatch.setattr(graph, 'run_extract_graph', fake_capture(config, captures))
    async def review(path, **kwargs):
        reviews.append(str(path))
        if len(reviews) == 1:
            raise ValueError('Transient model failure')
    monkeypatch.setattr(graph, 'run_ai_review_graph', review)
    job = batches.create_batch(['https://example.com/retry'], mode='review')
    await drain()
    assert batches.jobs[job['id']]['items'][0]['stage'] == 'review'
    assert batches.jobs[job['id']]['status'] == 'failed'
    batches.control_batch(job['id'], 'retry')
    await drain()
    assert batches.jobs[job['id']]['status'] == 'succeeded'
    assert len(captures) == 1 and len(reviews) == 2
    stored = next(j for j in JobStore().list() if j['id'] == job['id'])
    assert stored['items'][0]['status'] == 'succeeded'


@pytest.mark.asyncio
async def test_pause_and_cancel_leave_completed_work_intact(web_client, monkeypatch):
    _, config, _ = web_client
    from src.graph import graph
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    capture = fake_capture(config, calls)
    async def delayed(url):
        entered.set()
        await release.wait()
        return await capture(url)
    monkeypatch.setattr(graph, 'run_extract_graph', delayed)
    job = batches.create_batch(['https://example.com/a', 'https://example.com/b'])
    await entered.wait()
    batches.control_batch(job['id'], 'pause')
    release.set()
    await drain()
    assert batches.jobs[job['id']]['status'] == 'paused'
    assert [i['status'] for i in batches.jobs[job['id']]['items']] == ['succeeded', 'pending']
    batches.control_batch(job['id'], 'cancel')
    assert [i['status'] for i in batches.jobs[job['id']]['items']] == ['succeeded', 'cancelled']
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_cross_batch_duplicate_runs_once(web_client, monkeypatch):
    _, config, _ = web_client
    from src.graph import graph
    calls = []
    capture = fake_capture(config, calls)
    async def delayed(url):
        await asyncio.sleep(.02)
        return await capture(url)
    monkeypatch.setattr(graph, 'run_extract_graph', delayed)
    first = batches.create_batch(['https://example.com/one'])
    second = batches.create_batch(['https://example.com/one'])
    await drain()
    assert len(calls) == 1
    assert batches.jobs[first['id']]['items'][0]['status'] == 'succeeded'
    assert batches.jobs[second['id']]['items'][0]['status'] == 'skipped'


def test_interrupted_batch_requires_explicit_resume(web_client):
    stored = {'id': 'old-batch', 'kind': 'batch', 'status': 'running', 'items': [{'id': 'item', 'status': 'running', 'url': 'https://example.com/old'}]}
    JobStore().save(stored)
    web.recover_background_jobs()
    assert batches.jobs['old-batch']['status'] == 'failed'
    assert batches.jobs['old-batch']['interrupted']
    assert not web._background_tasks


@pytest.mark.asyncio
async def test_changed_configuration_does_not_start_model_work(web_client, monkeypatch):
    _, config, _ = web_client
    from src.graph import graph
    calls = []
    monkeypatch.setattr(graph, 'run_extract_graph', fake_capture(config, calls))
    job = batches.create_batch(['https://example.com/config-change'])
    monkeypatch.setattr(batches, 'configuration_fingerprint', lambda: 'changed')
    await drain()
    assert batches.jobs[job['id']]['status'] == 'failed'
    assert not calls


@pytest.mark.asyncio
async def test_retry_can_target_one_failed_item(web_client, monkeypatch):
    _, config, _ = web_client
    from src.graph import graph
    calls = []
    async def fail(url):
        raise ValueError('Temporary failure')
    monkeypatch.setattr(graph, 'run_extract_graph', fail)
    job = batches.create_batch(['https://example.com/first', 'https://example.com/second'])
    await drain()
    monkeypatch.setattr(graph, 'run_extract_graph', fake_capture(config, calls))
    batches.control_batch(job['id'], 'retry', [job['items'][1]['id']])
    await drain()
    assert calls == ['https://example.com/second']
    assert [i['status'] for i in batches.jobs[job['id']]['items']] == ['failed', 'succeeded']


@pytest.mark.asyncio
async def test_restart_resume_keeps_completed_capture_stage(web_client, monkeypatch):
    _, config, _ = web_client
    from src.graph import graph
    calls = []
    capture = fake_capture(config, calls)
    path = await capture('https://example.com/interrupted')
    from src.core.workspace import content_revision
    job = {'id': 'resume-batch', 'kind': 'batch', 'status': 'running', 'mode': 'review', 'perspective': 'original', 'language': 'source', 'collectionId': '', 'configurationFingerprint': batches.configuration_fingerprint(), 'items': [{'id': 'resume-item', 'url': 'https://example.com/interrupted', 'status': 'running', 'stage': 'review', 'articleId': path.parent.name, 'revision': content_revision(path.parent)}]}
    JobStore().save(job)
    web.recover_background_jobs()
    reviews = []
    async def review(path, **kwargs):
        reviews.append(str(path))
    monkeypatch.setattr(graph, 'run_ai_review_graph', review)
    batches.control_batch(job['id'], 'resume')
    await drain()
    assert len(calls) == 1 and len(reviews) == 1
    assert batches.jobs[job['id']]['status'] == 'succeeded'


def test_batch_is_available_through_shared_job_endpoints(web_client):
    client, _, _ = web_client
    response = client.post('/api/v1/batches', json={'urls': ['https://mp.weixin.qq.com/s/example']})
    assert response.status_code == 202
    job_id = response.json()['id']
    assert client.get('/api/v1/jobs/' + job_id).json()['kind'] == 'batch'
    listing = client.get('/api/v1/jobs?kind=batch')
    assert listing.status_code == 200
    assert job_id in {job['id'] for job in listing.json()['jobs']}
