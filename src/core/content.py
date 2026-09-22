"""Database mirror of article workspace content with loss recovery.

Article Markdown (raw.md / reviewed.md / reflection.md) and annotations.json
remain file-based; this module mirrors their content into the
``noosphere_article_content`` table (PostgreSQL or the local SQLite runtime)
so a lost workspace can be reconstructed from the database backup.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from src.core.config.config import load_config
from src.core.paths import runtime_home

logger = logging.getLogger(__name__)

_CONTENT_FIELDS = (
    "title",
    "source_url",
    "raw_markdown",
    "reviewed_markdown",
    "reflection_markdown",
    "annotations_json",
    "manifest_json",
    "review_json",
    "present_files_json",
)


class ArticleContentStore:
    """Mirror article Markdown content in PostgreSQL or the local SQLite runtime."""

    def __init__(self) -> None:
        config = load_config()
        self._postgres_url = (
            config.checkpoint.effective_postgres_connection_string()
            if config.checkpoint.is_postgres
            else None
        )
        self._sqlite_path = runtime_home() / "article_content.sqlite3"

    def _connect(self):
        if self._postgres_url:
            import psycopg
            from psycopg.rows import dict_row

            return psycopg.connect(self._postgres_url, row_factory=dict_row)
        self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._sqlite_path)
        connection.row_factory = sqlite3.Row
        return connection

    @property
    def _placeholder(self) -> str:
        return "%s" if self._postgres_url else "?"

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS noosphere_article_content (
                    article_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    raw_markdown TEXT NOT NULL DEFAULT '',
                    reviewed_markdown TEXT NOT NULL DEFAULT '',
                    reflection_markdown TEXT NOT NULL DEFAULT '',
                    annotations_json TEXT NOT NULL DEFAULT '',
                    manifest_json TEXT NOT NULL DEFAULT '',
                    review_json TEXT NOT NULL DEFAULT '',
                    present_files_json TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                )
                """
            )

            if self._postgres_url:
                for name in ("manifest_json", "review_json", "present_files_json"):
                    connection.execute(f"ALTER TABLE noosphere_article_content ADD COLUMN IF NOT EXISTS {name} TEXT NOT NULL DEFAULT ''")
            else:
                columns = {row["name"] for row in connection.execute("PRAGMA table_info(noosphere_article_content)")}
                for name in ("manifest_json", "review_json", "present_files_json"):
                    if name not in columns:
                        connection.execute(f"ALTER TABLE noosphere_article_content ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
            connection.execute("CREATE TABLE IF NOT EXISTS noosphere_article_deletions (article_id TEXT PRIMARY KEY, deleted_at TEXT NOT NULL)")

    def is_deleted(self, article_id: str) -> bool:
        self.ensure_schema()
        with self._connect() as connection:
            return connection.execute(f"SELECT article_id FROM noosphere_article_deletions WHERE article_id = {self._placeholder}", (article_id,)).fetchone() is not None

    def mark_deleted(self, article_id: str) -> None:
        self.ensure_schema()
        marker = self._placeholder
        with self._connect() as connection:
            connection.execute(f"INSERT INTO noosphere_article_deletions (article_id, deleted_at) VALUES ({marker}, {marker}) ON CONFLICT(article_id) DO NOTHING", (article_id, datetime.now(UTC).isoformat()))

    def upsert_content(
        self,
        article_id: str,
        *,
        title: str | None = None,
        source_url: str | None = None,
        raw_markdown: str | None = None,
        reviewed_markdown: str | None = None,
        reflection_markdown: str | None = None,
        annotations_json: str | None = None,
        manifest_json: str | None = None,
        review_json: str | None = None,
        present_files_json: str | None = None,
    ) -> None:
        """Insert or update the mirrored content; ``None`` fields stay unchanged."""
        self.ensure_schema()
        if self.is_deleted(article_id):
            raise ValueError("Article has been permanently deleted")
        marker = self._placeholder
        provided = {
            "title": title,
            "source_url": source_url,
            "raw_markdown": raw_markdown,
            "reviewed_markdown": reviewed_markdown,
            "reflection_markdown": reflection_markdown,
            "annotations_json": annotations_json,
            "manifest_json": manifest_json,
            "review_json": review_json,
            "present_files_json": present_files_json,
        }
        updated_at = datetime.now(UTC).isoformat()
        assignments = ", ".join(
            f"{name} = {marker}" for name, value in provided.items() if value is not None
        )
        if assignments:
            assignments += ", "
        assignments += f"updated_at = {marker}"
        insert_values = [article_id]
        insert_values.extend(provided[name] or "" for name in _CONTENT_FIELDS)
        insert_values.append(updated_at)
        update_values = [value for value in provided.values() if value is not None]
        update_values.append(updated_at)
        with self._connect() as connection:
            connection.execute(
                f"""
                INSERT INTO noosphere_article_content
                    (article_id, title, source_url, raw_markdown, reviewed_markdown,
                     reflection_markdown, annotations_json, manifest_json, review_json, present_files_json, updated_at)
                VALUES ({", ".join([marker] * (len(_CONTENT_FIELDS) + 2))})
                ON CONFLICT(article_id) DO UPDATE SET {assignments}
                """,
                (*insert_values, *update_values),
            )

    def get_content(self, article_id: str) -> dict[str, str] | None:
        """Return the mirrored content row for *article_id*, or ``None``."""
        self.ensure_schema()
        marker = self._placeholder
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT article_id, title, source_url, raw_markdown, reviewed_markdown,
                       reflection_markdown, annotations_json, manifest_json, review_json, present_files_json, updated_at
                FROM noosphere_article_content
                WHERE article_id = {marker}
                """,
                (article_id,),
            ).fetchone()
        return {key: str(value or "") for key, value in dict(row).items()} if row else None

    def delete_content(self, article_id: str) -> None:
        """Remove the mirrored content row for *article_id*."""
        self.ensure_schema()
        marker = self._placeholder
        with self._connect() as connection:
            connection.execute(
                f"DELETE FROM noosphere_article_content WHERE article_id = {marker}",
                (article_id,),
            )

    def list_article_ids(self) -> set[str]:
        """Return every article id present in the content mirror."""
        self.ensure_schema()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT article_id FROM noosphere_article_content"
            ).fetchall()
        return {str(row["article_id"]) for row in rows}


def mirror_content(article_id: str, **fields: str | None) -> None:
    """Mirror changes and retain a visible, retryable health record on failure."""
    from src.core.workspace import atomic_write_text, validate_article_id

    validate_article_id(article_id)
    article_dir = load_config().output_dir_path / article_id
    status_path = runtime_home() / "mirror-status" / f"{article_id}.json"
    try:
        for name, field in (("manifest.json", "manifest_json"), ("review.json", "review_json")):
            if (article_dir / name).is_file():
                fields[field] = (article_dir / name).read_text(encoding="utf-8")
        names = ("raw.md", "reviewed.md", "reflection.md", "annotations.json", "manifest.json", "review.json")
        if article_dir.is_dir():
            fields["present_files_json"] = json.dumps([name for name in names if (article_dir / name).is_file()])
        ArticleContentStore().upsert_content(article_id, **fields)
        status = {"status": "synced", "updatedAt": datetime.now(UTC).isoformat()}
    except Exception as exc:
        logger.warning("Article content mirror failed for %s: %s", article_id, exc)
        status = {"status": "failed", "updatedAt": datetime.now(UTC).isoformat(), "error": "Database mirror update failed; retry after restoring database access."}
    try:
        atomic_write_text(status_path, json.dumps(status))
    except OSError:
        logger.warning("Could not persist mirror health for %s", article_id)


def mirror_status(article_id: str) -> dict:
    from src.core.workspace import read_json, validate_article_id

    validate_article_id(article_id)
    return read_json(runtime_home() / "mirror-status" / f"{article_id}.json") or {"status": "unknown"}


def retry_mirror(article_id: str) -> dict:
    from src.core.workspace import safe_article_dir, article_lock

    with article_lock(article_id):
        article_dir = safe_article_dir(article_id)
        fields = {}
        for name, field in (("raw.md", "raw_markdown"), ("reviewed.md", "reviewed_markdown"), ("reflection.md", "reflection_markdown"), ("annotations.json", "annotations_json")):
            if (article_dir / name).is_file():
                fields[field] = (article_dir / name).read_text(encoding="utf-8")
        mirror_content(article_id, **fields)
        return mirror_status(article_id)


def mirror_delete(article_id: str) -> None:
    """Never report success while a recoverable content row remains."""
    ArticleContentStore().delete_content(article_id)


def reconstruct_article_workspace(article_id: str, output_dir: Path) -> Path | None:
    """Rebuild a missing article workspace from the database mirror.

    Only files that are absent are written; existing files are never
    overwritten. Trashed articles are skipped (their workspace lives in the
    trash directory, not the output directory). Asset images are not
    restored. Returns the article directory when a database backup exists,
    otherwise ``None``.
    """
    try:
        from src.core.trash import ArticleTrashStore

        if ArticleTrashStore().get(article_id) is not None:
            return None
        store = ArticleContentStore()
        if store.is_deleted(article_id):
            return None
        row = store.get_content(article_id)
    except Exception as exc:
        logger.warning("Article content backup unavailable for %s: %s", article_id, exc)
        return None
    if not row:
        return None
    from src.core.workspace import validate_article_id

    validate_article_id(article_id)
    article_dir = (Path(output_dir) / article_id).resolve()
    if article_dir.parent != Path(output_dir).resolve():
        raise ValueError("Invalid article workspace")
    article_dir.mkdir(parents=True, exist_ok=True)

    present = set(json.loads(row.get("present_files_json") or "[]"))

    def _write_if_missing(name: str, content: str) -> None:
        path = article_dir / name
        if (content or name in present) and not path.exists():
            # Exclusive creation prevents recovery from replacing a concurrent save.
            try:
                with path.open("x", encoding="utf-8") as handle:
                    handle.write(content)
            except FileExistsError:
                pass

    _write_if_missing("raw.md", row["raw_markdown"])
    _write_if_missing("reviewed.md", row["reviewed_markdown"])
    _write_if_missing("reflection.md", row["reflection_markdown"])
    _write_if_missing("annotations.json", row["annotations_json"])
    _write_if_missing("review.json", row.get("review_json", ""))
    _write_if_missing("manifest.json", row.get("manifest_json", ""))
    manifest_path = article_dir / "manifest.json"
    if not manifest_path.exists():
        manifest = {
            "schema_version": 1,
            "article_id": article_id,
            "article": {
                "platform": "",
                "platform_label": "",
                "url": row["source_url"],
                "title": row["title"],
                "author": "",
                "published_at": "",
                "captured_at": row["updated_at"],
                "content_type": "article",
                "extra": {},
            },
            "paths": {
                "raw": "raw.md",
                "reviewed": "reviewed.md",
                "assets": "assets",
                "manifest": "manifest.json",
            },
            "assets": {"downloaded": [], "failed": {}},
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    logger.info("reconstructed article %s from database backup", article_id)
    return article_dir


def recover_missing_article_workspaces(output_dir: Path) -> int:
    """Rebuild workspaces missing from *output_dir*; return how many were recovered."""
    try:
        article_ids = ArticleContentStore().list_article_ids()
    except Exception as exc:
        logger.warning("Article content backup unavailable during startup check: %s", exc)
        return 0
    recovered = 0
    for article_id in sorted(article_ids):
        from src.core.workspace import article_lock

        with article_lock(article_id):
            directory = Path(output_dir) / article_id
            before = {p.name for p in directory.iterdir()} if directory.is_dir() else set()
            if reconstruct_article_workspace(article_id, output_dir) is not None:
                after = {p.name for p in directory.iterdir()}
                recovered += int(bool(after - before))
    logger.info(
        "Startup article content check: recovered %d article workspace(s) from database backup",
        recovered,
    )
    return recovered
