"""Isolate cancellable review changes until the complete article is ready."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from src.core.paths import runtime_home
from src.core.workspace import article_lock, atomic_write_text, check_revision, content_revision, read_json

_pending: ContextVar[ReviewTransaction | None] = ContextVar("pending_review", default=None)


def pending_review(article_id: str) -> ReviewTransaction | None:
    transaction = _pending.get()
    return transaction if transaction and transaction.article_id == article_id else None


async def joined_worker(function, *args):
    """A cancelled review must join its disk writer before deleting the staging area."""
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
        task.result()
        raise


class ReviewTransaction:
    def __init__(self, article_dir: Path):
        self.article_dir = article_dir
        self.article_id = article_dir.name
        self.root: Path | None = None
        self.staged: Path | None = None
        self.revision = ""
        self.assignment: dict[str, Any] | None = None
        self.original_assignment: dict[str, Any] | None = None
        self.activities: list[tuple[str, dict[str, Any]]] = []
        self._token = None

    def prepare(self) -> None:
        from src.core.collections import CollectionStore

        root = runtime_home() / "pending-reviews"
        root.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(dir=root))
        self.staged = self.root / self.article_id
        with article_lock(self.article_id):
            self.revision = content_revision(self.article_dir)
            self.original_assignment = CollectionStore().get_assignment(self.article_id)
            shutil.copytree(self.article_dir, self.staged)

    async def __aenter__(self):
        try:
            await joined_worker(self.prepare)
        except BaseException:
            await joined_worker(self.cleanup)
            raise
        self._token = _pending.set(self)
        return self

    async def __aexit__(self, *_):
        _pending.reset(self._token)
        await joined_worker(self.cleanup)

    def cleanup(self) -> None:
        if self.root:
            shutil.rmtree(self.root, ignore_errors=True)

    def stage_assignment(self, **assignment) -> dict[str, Any]:
        from src.core.collections import CollectionStore

        self.assignment = assignment
        path = CollectionStore().get_path(assignment["collection_id"]) if assignment["collection_id"] else []
        return {"article_id": self.article_id, **assignment, "collection_path": path,
                "collection_name": path[-1]["name"] if path else None}

    def publish(self) -> None:
        """Publish without an async cancellation point, preserving unrelated sidecars."""
        from src.core.activity import ArticleActivityStore
        from src.core.collections import CollectionStore
        from src.core.content import mirror_content
        from src.core.library import invalidate_summaries

        assert self.staged and self.root
        with article_lock(self.article_id):
            check_revision(self.article_dir, self.revision)
            manifest = read_json(self.article_dir / "manifest.json")
            reviewed_manifest = read_json(self.staged / "manifest.json")
            for key in ("article", "image_filter", "metadata_enrichment"):
                if key in reviewed_manifest:
                    manifest[key] = reviewed_manifest[key]
                else:
                    manifest.pop(key, None)
            atomic_write_text(self.staged / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
            backup = self.root / "backup"
            backup.mkdir()
            replaced: list[tuple[Path, Path, bool]] = []
            token = _pending.set(None)
            try:
                for name in ("reviewed.md", "review.json", "manifest.json", "assets", "removed"):
                    target, source, previous = self.article_dir / name, self.staged / name, backup / name
                    existed = target.exists()
                    if existed:
                        os.replace(target, previous)
                    replaced.append((target, previous, existed))
                    if source.exists():
                        os.replace(source, target)
                store = CollectionStore()
                if self.assignment and store.get_assignment(self.article_id) == self.original_assignment:
                    store.assign_article(self.article_id, **self.assignment)
            except BaseException:
                for target, previous, existed in reversed(replaced):
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink(missing_ok=True)
                    if existed:
                        os.replace(previous, target)
                raise
            else:
                for event, details in self.activities:
                    ArticleActivityStore().record(self.article_id, event, **details)
                mirror_content(self.article_id, reviewed_markdown=(self.article_dir / "reviewed.md").read_text(encoding="utf-8"))
                invalidate_summaries()
            finally:
                _pending.reset(token)
