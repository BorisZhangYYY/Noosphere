"""Localized article summaries shared by the Web, CLI and MCP interfaces."""
from __future__ import annotations
import copy
import time
from collections import OrderedDict
from threading import RLock
from src.core.config.config import load_config
from src.core.paths import runtime_home
import logging
import re
from pathlib import Path
from typing import Any
from src.core.workspace import read_json as _read_json
from src.core.markdown.cleaner import extract_title_from_markdown
logger = logging.getLogger(__name__)
_exception_message = str

def _article_status(article_dir: Path, manifest: dict[str, Any]) -> str:
    if manifest.get("error"):
        return "failed"
    if (manifest.get("uploaded") or {}).get("hpath"):
        return "uploaded"
    review = _read_json(article_dir / "review.json")
    if review.get("status") == "reviewed":
        return "reviewed"
    return "captured"


def _build_article_summary(manifest_path: Path, locale: str = "en-US") -> dict[str, Any] | None:
    manifest = _read_json(manifest_path)
    if not manifest:
        return None
    article = manifest.get("article") or {}
    downloaded = (manifest.get("assets") or {}).get("downloaded") or []
    reviewed_path = manifest_path.parent / "reviewed.md"
    raw_path = manifest_path.parent / "raw.md"
    display_title = (
        _markdown_title(reviewed_path)
        or _markdown_title(raw_path)
        or str(article.get("title") or manifest_path.parent.name)
    )
    metadata = _markdown_metadata(reviewed_path)
    if not metadata:
        metadata = _markdown_metadata(raw_path)
    raw_markdown = raw_path.read_text(encoding="utf-8") if raw_path.is_file() else ""
    from src.core.article_metadata import article_metadata_state

    protected_metadata = article_metadata_state(manifest, raw_markdown)
    article_id = str(manifest.get("article_id") or manifest_path.parent.name)
    collection = None
    collection_search_terms: list[str] = []
    operations = {
        "captureCount": 0,
        "reviewCount": 0,
        "rereviewCount": 0,
        "uploadCount": 0,
        "reflectCount": 0,
        "events": [],
    }
    try:
        from src.core.collections import CollectionStore

        collection_store = CollectionStore()
        collection = collection_store.get_assignment(article_id, locale=locale)
        collection_search_terms = [str(item["name"]) for item in (collection or {}).get("collection_path", [])]
    except Exception as exc:
        logger.warning("Article collection unavailable for %s: %s", article_id, _exception_message(exc))
    try:
        from src.core.activity import ArticleActivityStore

        activity = ArticleActivityStore()
        activity.backfill_workspace(article_id, manifest, _read_json(manifest_path.parent / "review.json"))
        operations = activity.summary(article_id, limit=0)
    except Exception as exc:
        logger.warning("Article activity unavailable for %s: %s", article_id, _exception_message(exc))
    return {
        "id": article_id,
        "title": display_title,
        "url": str(article.get("url") or ""),
        "platform": str(article.get("platform") or "unknown"),
        "platformLabel": str(article.get("platform_label") or article.get("platform") or "Unknown"),
        "author": protected_metadata["author"]["value"],
        "capturedAt": article.get("captured_at"),
        "status": _article_status(manifest_path.parent, manifest),
        "assetsCount": len(downloaded),
        "collection": collection,
        "operationSummary": operations,
        "searchTerms": [value for value in [display_title, article.get("title"), protected_metadata["author"]["value"], article.get("platform_label"), *collection_search_terms] if value],
    }


def _markdown_title(path: Path) -> str | None:
    """Read the first Markdown H1 so edited and reviewed titles stay current."""
    if not path.is_file():
        return None
    try:
        return extract_title_from_markdown(path.read_text(encoding="utf-8")[:12000])
    except OSError:
        return None


def _markdown_metadata(path: Path) -> dict[str, str]:
    """Read source metadata from the leading Markdown blockquote as a fallback."""
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")[:12000]
    except OSError:
        return {}
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith(">"):
            continue
        content = line.lstrip("> ").strip()
        if ":" not in content:
            continue
        key, value = content.split(":", 1)
        normalized = key.strip().strip("*_`").casefold()
        if normalized in {"author", "published", "captured", "platform", "type"}:
            fields[normalized] = value.strip().strip("*_`")
    return fields




_summary_cache: OrderedDict = OrderedDict()
_cache_lock = RLock()
_cache_generation = 0


def invalidate_summaries() -> None:
    """Invalidate metadata after database writes, including in-flight reads."""
    global _cache_generation
    with _cache_lock:
        _cache_generation += 1
        _summary_cache.clear()


def _stamp(path: Path) -> tuple:
    try:
        stat = path.stat()
        return (stat.st_mtime_ns, stat.st_size)
    except OSError:
        return (0, 0)


def _article_summary(manifest_path: Path, locale: str = "en-US") -> dict | None:
    """Reuse unchanged summaries; PostgreSQL metadata expires after one second."""
    config = load_config()
    home = runtime_home()
    storage = tuple(_stamp(home / name) for name in ("catalog.sqlite3", "catalog.sqlite3-wal", "activity.sqlite3", "activity.sqlite3-wal"))
    key = (str(manifest_path.resolve()), str(home.resolve()), locale)
    stamp = (tuple(_stamp(manifest_path.parent / name) for name in ("manifest.json", "raw.md", "reviewed.md", "review.json")), storage)
    with _cache_lock:
        generation = _cache_generation
        entry = _summary_cache.get(key)
        if entry and entry[0] == stamp and (not config.checkpoint.is_postgres or time.monotonic() - entry[1] < 1):
            _summary_cache.move_to_end(key)
            return copy.deepcopy(entry[2])
    result = _build_article_summary(manifest_path, locale)
    # Building legacy summaries can backfill activity records.
    storage = tuple(_stamp(home / name) for name in ("catalog.sqlite3", "catalog.sqlite3-wal", "activity.sqlite3", "activity.sqlite3-wal"))
    with _cache_lock:
        if generation != _cache_generation:
            return result
        _summary_cache[key] = ((stamp[0], storage), time.monotonic(), copy.deepcopy(result))
        _summary_cache.move_to_end(key)
        while len(_summary_cache) > 4096:
            _summary_cache.popitem(last=False)
    return result
