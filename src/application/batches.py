"""Durable, explicitly resumed batches using the shared bounded job runner."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import uuid
import weakref
from urllib.parse import urlsplit, urlunsplit

from src.core.config.config import load_config
from src.core.jobs import JobStore
from src.core.workspace import safe_article_dir, content_revision

jobs: dict[str, dict] = {}
_url_locks = weakref.WeakKeyDictionary()


def normalize_url(value: str) -> str:
    from src.mcp.server import _validate_url
    parsed = urlsplit(_validate_url(value))
    if parsed.username or parsed.password or not parsed.hostname:
        raise ValueError("URLs must have a host and no embedded credentials")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or '/', parsed.query, ''))


def configuration_fingerprint() -> str:
    return hashlib.sha256(json.dumps(load_config().model_dump(mode='json'), sort_keys=True).encode()).hexdigest()


def preflight(urls: list[str]) -> list[dict]:
    from src.application.service import list_articles
    if not isinstance(urls, list) or not 1 <= len(urls) <= 100:
        raise ValueError("Provide between 1 and 100 URLs")
    existing = {}
    for article in list_articles():
        try:
            existing[normalize_url(article['url'])] = article['id']
        except ValueError:
            pass
    seen = set()
    items = []
    for value in urls:
        item = {'id': uuid.uuid4().hex, 'url': value if isinstance(value, str) else '', 'status': 'pending', 'stage': 'capture', 'articleId': None, 'error': None}
        try:
            if not isinstance(value, str) or len(value) > 8192:
                raise ValueError('Invalid URL length')
            url = normalize_url(value)
            item['url'] = url
            if url in seen:
                item.update(status='skipped', reason='duplicate')
            elif url in existing:
                item.update(status='skipped', reason='existing', articleId=existing[url])
            seen.add(url)
        except (ValueError, TypeError) as exc:
            item.update(status='invalid', error=str(exc))
        items.append(item)
    return items


def create_batch(urls: list[str], *, mode: str = 'capture', perspective: str | None = None, language: str = 'source', collection_id: str = '') -> dict:
    from src.api import web
    config = load_config()
    if mode not in {'capture', 'review'}:
        raise ValueError('Mode must be capture or review')
    if language not in {'source', 'zh-CN', 'en-US'}:
        raise ValueError('Unsupported output language')
    selected = perspective or config.pipeline.active_perspective
    if selected not in config.pipeline.perspectives:
        raise ValueError('Unknown review perspective')
    if collection_id:
        from src.core.collections import CollectionStore
        if CollectionStore().get_collection(collection_id) is None:
            raise ValueError('Active collection not found')
    web._check_job_capacity()
    if sum(j['status'] in {'queued', 'running', 'paused'} for j in jobs.values()) >= 100:
        raise ValueError('Too many unfinished batches; finish or cancel an existing batch')
    job = {'id': uuid.uuid4().hex, 'kind': 'batch', 'status': 'queued', 'createdAt': web._utc_now(), 'mode': mode, 'perspective': selected, 'language': language, 'collectionId': collection_id, 'provider': config.ai.provider, 'configurationFingerprint': configuration_fingerprint(), 'items': preflight(urls), 'pauseRequested': False, 'cancelRequested': False}
    jobs[job['id']] = job
    web._queue_job(jobs, job['id'], run_batch)
    return copy.deepcopy(job)


async def _persist(job: dict):
    await asyncio.to_thread(JobStore().save, copy.deepcopy(job))


async def run_batch(job_id: str):
    from src.api import web
    from src.graph.graph import run_extract_graph, run_ai_review_graph
    from src.application.service import place_article, list_articles
    job = jobs[job_id]
    job.update(status='running', error=None)
    try:
        for item in job['items']:
            if item['status'] != 'pending':
                continue
            if job['cancelRequested'] or job['pauseRequested']:
                break
            locks = _url_locks.setdefault(asyncio.get_running_loop(), {})
            lock = locks.setdefault(item['url'], asyncio.Lock())
            async with lock:
                if job['cancelRequested'] or job['pauseRequested']:
                    break
                item.update(status='running', error=None)
                await _persist(job)
                try:
                    if job['configurationFingerprint'] != configuration_fingerprint():
                        raise ValueError('Configuration changed since submission. Restore it or create a new batch.')
                    if not item['articleId']:
                        existing = next((a for a in await asyncio.to_thread(list_articles) if a['url'] and normalize_url(a['url']) == item['url']), None)
                        if existing:
                            item.update(status='skipped', reason='existing', articleId=existing['id'])
                            await _persist(job)
                            continue
                        path = await run_extract_graph(item['url'])
                        item.update(articleId=path.parent.name, stage='review' if job['mode'] == 'review' else 'placement', revision=content_revision(path.parent))
                        await _persist(job)
                    folder = safe_article_dir(item['articleId'])
                    if job['configurationFingerprint'] != configuration_fingerprint():
                        raise ValueError('Configuration changed during processing; restore it before retrying.')
                    if item['stage'] == 'review':
                        if job['pauseRequested'] or job['cancelRequested']:
                            item['status'] = 'pending'
                            break
                        if item.get('revision') != content_revision(folder):
                            raise ValueError('Article changed since capture; review this article individually.')
                        await run_ai_review_graph(folder / 'reviewed.md', perspective=job['perspective'], output_language=job['language'], source_markdown=(folder / 'reviewed.md').read_text(encoding='utf-8'))
                        item['stage'] = 'placement'
                        await _persist(job)
                    if job['collectionId']:
                        await asyncio.to_thread(place_article, item['articleId'], collection_id=job['collectionId'])
                    item.update(status='succeeded', stage='completed')
                except Exception as exc:
                    item.update(status='failed', error=str(exc))
                await _persist(job)
        if job['cancelRequested']:
            for item in job['items']:
                if item['status'] == 'pending':
                    item['status'] = 'cancelled'
            job['status'] = 'cancelled'
        elif job['pauseRequested'] and any(i['status'] == 'pending' for i in job['items']):
            job['status'] = 'paused'
        else:
            job['status'] = 'failed' if any(i['status'] in {'failed', 'invalid'} for i in job['items']) else 'succeeded'
        job['finishedAt'] = web._utc_now()
    except asyncio.CancelledError:
        for item in job['items']:
            if item['status'] == 'running':
                item.update(status='failed', error='Service interrupted this stage. Retry explicitly.')
        raise
    finally:
        await _persist(job)


def control_batch(job_id: str, action: str, item_ids: list[str] | None = None) -> dict:
    from src.api import web
    if job_id not in jobs:
        raise ValueError('Batch not found')
    job = jobs[job_id]
    if item_ids is not None and (action != 'retry' or not isinstance(item_ids, list) or not item_ids or any(not isinstance(i, str) for i in item_ids) or not set(item_ids).issubset({i['id'] for i in job['items']})):
        raise ValueError('Provide valid item IDs for retry')
    active = job['status'] in {'running', 'queued'}
    if action in {'pause', 'cancel'}:
        if active:
            job['pauseRequested' if action == 'pause' else 'cancelRequested'] = True
        elif action == 'cancel':
            for item in job['items']:
                if item['status'] in {'pending', 'failed', 'running'}:
                    item['status'] = 'cancelled'
            job['status'] = 'cancelled'
    elif action in {'resume', 'retry'}:
        if active:
            raise ValueError('Wait until the current batch stops before resuming')
        if job['status'] == 'cancelled':
            raise ValueError('Cancelled batches cannot be resumed; submit selected URLs again')
        if job['configurationFingerprint'] != configuration_fingerprint():
            raise ValueError('Configuration changed since submission; restore it or create a new batch')
        web._check_job_capacity()
        for item in job['items']:
            if item['status'] == 'running' or (action == 'retry' and item['status'] == 'failed' and (item_ids is None or item['id'] in item_ids)):
                item['status'] = 'pending'
        if not any(i['status'] == 'pending' for i in job['items']):
            raise ValueError('No pending items; use retry for failed items')
        job.update(status='queued', pauseRequested=False, cancelRequested=False, interrupted=False)
        web._queue_job(jobs, job_id, run_batch)
    else:
        raise ValueError('Unknown batch action')
    JobStore().save(job)
    return copy.deepcopy(job)
