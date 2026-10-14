"""Rebuildable local full-text index; article files remain authoritative."""
from __future__ import annotations

import fcntl
from contextlib import contextmanager
import hashlib
import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from datetime import date
from threading import RLock

from src.core.config.config import load_config
from src.core.paths import runtime_home
from src.core.workspace import article_lock
from src.core.article_metadata import editable_article_markdown

_LOCK = RLock()
_FIELDS = {"reviewed"}
_FILES = ("reviewed.md",)
_INDEX_VERSION = "reviewed-body-v2"
_LOCAL_IMAGE_RE = re.compile(r'!\[([^\]]*)\]\((assets/[^\s)]+)\)')
_MARKDOWN_RESOURCE_RE = re.compile(r'!?\[[^\]\n]*\]\([^\n)]*\)')


def terms(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return re.findall(r"[\u3400-\u9fff]|[^\W_]+", re.sub(r"([\u3400-\u9fff])", r" \1 ", normalized), re.UNICODE)


def encoded(text: str) -> str:
    return " ".join("t" + word.encode().hex() for word in terms(text))


def query_parts(query: str) -> list[str]:
    if len(query) > 500:
        raise ValueError("Search query must be at most 500 characters")
    parts = [quoted or word for quoted, word in re.findall(r'"([^\"]+)"|(\S+)', query)]
    parts = [p for p in parts if terms(p)]
    if len(parts) > 20:
        raise ValueError("Search supports at most 20 terms or phrases")
    return parts


@contextmanager
def _index_lock():
    with _LOCK:
        path = runtime_home() / 'locks' / 'search-index.lock'
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a') as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _connect():
    path = runtime_home() / "search.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE IF NOT EXISTS search_files (article_id TEXT PRIMARY KEY, stamp TEXT NOT NULL)")
        db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS search_passages USING fts5(article_id UNINDEXED, field UNINDEXED, original UNINDEXED, digest UNINDEXED, tokens)")
        with db:
            yield db
    finally:
        db.close()


def synchronize(*, rebuild: bool = False) -> dict:
    """Reconcile file signatures transactionally, including external edits/deletions."""
    output = load_config().output_dir_path.resolve()
    changed = 0
    with _index_lock():
        if rebuild:
            for name in ('search.sqlite3', 'search.sqlite3-wal', 'search.sqlite3-shm'):
                (runtime_home() / name).unlink(missing_ok=True)
        return _synchronize(output, changed)


def _synchronize(output, changed):
    from src.core.content import ArticleContentStore
    store = ArticleContentStore()
    store.ensure_schema()
    with store._connect() as connection:
        deleted = {row['article_id'] for row in connection.execute('SELECT article_id FROM noosphere_article_deletions').fetchall()}
    with _connect() as db:
        db.execute("DELETE FROM search_passages WHERE field <> 'reviewed'")
        known = {row["article_id"]: row["stamp"] for row in db.execute("SELECT * FROM search_files")}
        found = set()
        for manifest in sorted(output.glob("*/manifest.json")):
            folder = manifest.parent
            if folder.is_symlink() or manifest.is_symlink():
                continue
            article_id = folder.name
            if article_id in deleted:
                continue
            found.add(article_id)
            with article_lock(article_id):
                stamps = []
                for name in _FILES:
                    path = folder / name
                    if path.is_file() and not path.is_symlink():
                        stat = path.stat()
                        stamps.append((name, stat.st_mtime_ns, stat.st_size))
                stamp = json.dumps([_INDEX_VERSION, stamps])
                if known.get(article_id) == stamp:
                    continue
                path = folder / "reviewed.md"
                text = editable_article_markdown(path.read_text(encoding="utf-8")) if path.is_file() and not path.is_symlink() else ""
                if article_id in known:
                    db.execute("DELETE FROM search_passages WHERE article_id = ?", (article_id,))
                if text.strip():
                    db.execute("INSERT INTO search_passages VALUES (?, ?, ?, ?, ?)", (article_id, "reviewed", text, hashlib.sha256(text.encode()).hexdigest(), encoded(text)))
                db.execute("INSERT OR REPLACE INTO search_files VALUES (?, ?)", (article_id, stamp))
                changed += 1
        removed = set(known) - found
        for article_id in removed:
            db.execute("DELETE FROM search_passages WHERE article_id = ?", (article_id,))
            db.execute("DELETE FROM search_files WHERE article_id = ?", (article_id,))
        return {"articles": len(found), "updated": changed, "removed": len(removed)}


def excerpt(text: str, parts: list[str], *, field: str = "") -> dict:
    folded = text.casefold()
    body_start = 0
    if field in {"reviewed", "raw"}:
        header_end = re.search(r"(?m)^---[ \t]*\r?\n", text)
        if header_end and re.search(r"(?m)^>\s*(?:Source|Platform|Author|Published|Captured|Type)\s*[:：]", text[:header_end.start()], re.I):
            body_start = header_end.end()
    matches = [(folded.find(part.casefold(), body_start), len(part)) for part in parts if part.casefold() in folded[body_start:]]
    if not matches:
        matches = [(folded.find(part.casefold()), len(part)) for part in parts if part.casefold() in folded]
    position = min((p for p, _ in matches), default=0)
    start = max(body_start if position >= body_start else 0, position - 80)
    end = min(len(text), max(start + 280, position + 100))
    line_start = text.rfind("\n", body_start if position >= body_start else 0, start)
    if line_start >= 0 and start - line_start <= 320:
        start = line_start + 1
    line_end = text.find("\n", end)
    if line_end >= 0 and line_end - end <= 320:
        end = line_end
    preceding_blocks = list(re.finditer(r"\n[ \t]*\n", text[body_start:start]))
    if preceding_blocks:
        block_start = body_start + preceding_blocks[-1].end()
        if start - block_start <= 600:
            start = block_start
    following_block = re.search(r"\n[ \t]*\n", text[end:])
    if following_block and following_block.start() <= 600:
        end += following_block.start()
    for resource in _MARKDOWN_RESOURCE_RE.finditer(text):
        if resource.start() < end and resource.end() > start:
            start = min(start, resource.start())
            end = max(end, resource.end())
    snippet = text[start:end]
    highlights = []
    for part in parts:
        for match in re.finditer(re.escape(part), snippet, re.I):
            highlights.append([match.start(), match.end()])
    images = [
        {"alt": match.group(1), "path": match.group(2)}
        for match in _LOCAL_IMAGE_RE.finditer(text)
        if match.start() < end and match.end() > start
    ]
    return {"text": snippet, "start": start, "highlights": highlights, "images": images}


def search_articles(query: str, *, scope: str = "all", collection_id: str = "", platform: str = "", after: str = "", before: str = "", offset: int = 0, limit: int = 30, locale: str = "en-US") -> dict:
    from src.core.library import _article_summary

    if scope != "all" and scope not in _FIELDS:
        raise ValueError("Full-text search only supports reviewed article text")
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError("Invalid search pagination")
    for value in (after, before):
        if value:
            date.fromisoformat(value)
    if after and before and after > before:
        raise ValueError("Start date must not be after end date")
    parts = query_parts(query)
    index = synchronize()
    if not parts:
        return {"results": [], "total": 0, "index": index}
    expression = " AND ".join('"' + encoded(part) + '"' for part in parts)
    fields = ["reviewed"]

    with _index_lock(), _connect() as db:
        rows = db.execute(f"SELECT article_id, field, original, digest, bm25(search_passages) AS rank FROM search_passages WHERE search_passages MATCH ? AND field IN ({','.join('?' for _ in fields)}) ORDER BY rank", (expression, *fields)).fetchall()
    grouped = {}
    summaries = {}
    output = load_config().output_dir_path.resolve()
    for row in rows:
        article_id = row["article_id"]
        manifest = output / article_id / 'manifest.json'
        if not manifest.is_file():
            continue
        if article_id not in summaries:
            summaries[article_id] = _article_summary(manifest, locale)
        article = summaries[article_id]
        if not article or (platform and article['platform'] != platform):
            continue
        captured = str(article.get('capturedAt') or '')[:10]
        if (after and captured < after) or (before and captured > before):
            continue
        if collection_id and collection_id not in {node['id'] for node in (article.get('collection') or {}).get('collection_path', [])}:
            continue
        result = grouped.setdefault(article_id, {"article": article, "matches": []})
        if len(result["matches"]) < 6:
            result["matches"].append({"field": row["field"], "digest": row["digest"], **excerpt(row["original"], parts, field=row["field"])})
    return {"results": list(grouped.values())[offset:offset + limit], "total": len(grouped), "index": index}


def passage(article_id: str, field: str, digest: str, start: int = 0) -> dict:
    from src.core.workspace import safe_article_dir
    if field not in _FIELDS or start < 0:
        raise ValueError('Invalid passage location')
    safe_article_dir(article_id)
    synchronize()
    with _index_lock(), _connect() as db:
        row = db.execute('SELECT original, digest FROM search_passages WHERE article_id = ? AND field = ?', (article_id, field)).fetchone()
    if not row:
        raise ValueError('Passage is no longer available')
    changed = row['digest'] != digest
    if changed:
        return {'changed': True, 'text': '', 'field': field}
    text = row['original']
    return {'changed': False, 'field': field, 'text': text[max(0, start - 200):start + 1600]}
