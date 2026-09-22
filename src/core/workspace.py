"""Transport-independent workspace paths, atomic writes and write serialization."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
import threading
from contextlib import ExitStack, contextmanager
from functools import wraps
from inspect import signature
from pathlib import Path

from src.core.config.config import load_config
from src.core.paths import runtime_home

_guard = threading.Lock()
_locks: dict[str, threading.RLock] = {}
_depth = threading.local()


class RevisionConflict(ValueError):
    """The submitted draft was based on a different persisted revision."""


def validate_article_id(article_id: str) -> str:
    if not isinstance(article_id, str) or not article_id.strip() or article_id != article_id.strip():
        raise ValueError("Invalid article id")
    if article_id in {".", ".."} or "/" in article_id or "\\" in article_id or "\0" in article_id or Path(article_id).is_absolute():
        raise ValueError("Invalid article id")
    return article_id


@contextmanager
def article_lock(article_id: str):
    validate_article_id(article_id)
    root = runtime_home() / "locks"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{article_id}.lock"
    key = str(path.resolve())
    with _guard:
        lock = _locks.setdefault(key, threading.RLock())
    with lock:
        depths = getattr(_depth, "held", {})
        _depth.held = depths
        if depths.get(key):
            yield
            return
        with path.open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            depths[key] = True
            try:
                yield
            finally:
                del depths[key]
                fcntl.flock(handle, fcntl.LOCK_UN)


def serialized(function):
    first_parameter = next(iter(signature(function).parameters))

    @wraps(function)
    def wrapped(*args, **kwargs):
        article_id = args[0] if args else kwargs[first_parameter]
        ids = article_id if isinstance(article_id, list) else [article_id]
        with ExitStack() as stack:
            for key in sorted(set(ids)):
                stack.enter_context(article_lock(key))
            return function(*args, **kwargs)
    return wrapped


def atomic_write_text(destination: Path, content: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{destination.name}-", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def content_revision(article_dir: Path) -> str:
    digest = hashlib.sha256()
    for name in ("reviewed.md", "manifest.json"):
        path = article_dir / name
        digest.update(name.encode() + b"\0")
        if name == "manifest.json" and path.is_file():
            manifest = read_json(path)
            relevant = {key: manifest.get(key) for key in ("article", "paths", "image_filter", "metadata_enrichment")}
            digest.update(json.dumps(relevant, sort_keys=True, ensure_ascii=False).encode())
        else:
            digest.update(path.read_bytes() if path.is_file() else b"<missing>")
    for name in ("assets", "removed"):
        folder = article_dir / name
        digest.update(name.encode() + b"\0")
        if folder.is_dir():
            digest.update("\0".join(sorted(p.name for p in folder.iterdir() if p.is_file())).encode())
    return digest.hexdigest()


def check_revision(article_dir: Path, expected: str | None) -> None:
    if expected is not None and expected != content_revision(article_dir):
        raise RevisionConflict("Article changed since it was opened. Your draft has been preserved; reload and reconcile it before saving.")


@serialized
def safe_article_dir(article_id: str) -> Path:
    output = load_config().output_dir_path.resolve()
    article_dir = (output / validate_article_id(article_id)).resolve()
    if article_dir.parent != output:
        raise ValueError(f"Article not found: {article_id}")
    from src.core.content import reconstruct_article_workspace
    required = ("manifest.json", "raw.md", "reviewed.md", "reflection.md", "annotations.json", "review.json")
    if any(not (article_dir / name).is_file() for name in required):
        reconstruct_article_workspace(article_id, output)
    if not article_dir.is_dir() or not (article_dir / "manifest.json").is_file():
        raise ValueError(f"Article not found: {article_id}")
    return article_dir
