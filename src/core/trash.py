"""Persistent recycle-bin records for article workspaces."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from src.core.config.config import load_config
from src.core.paths import runtime_home


class ArticleTrashStore:
    """Track soft-deleted articles in PostgreSQL or the local SQLite runtime."""

    def __init__(self) -> None:
        config = load_config()
        self._postgres_url = (
            config.checkpoint.effective_postgres_connection_string()
            if config.checkpoint.is_postgres
            else None
        )
        self._sqlite_path = runtime_home() / "trash.sqlite3"

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
                CREATE TABLE IF NOT EXISTS noosphere_article_trash (
                    article_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL DEFAULT '',
                    deleted_at TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )

    def add(self, article_id: str, *, title: str, url: str, details: dict[str, Any]) -> dict[str, Any]:
        self.ensure_schema()
        marker = self._placeholder
        deleted_at = datetime.now(UTC).isoformat()
        payload = json.dumps(details, ensure_ascii=False)
        with self._connect() as connection:
            existing = connection.execute(
                f"SELECT article_id FROM noosphere_article_trash WHERE article_id = {marker}",
                (article_id,),
            ).fetchone()
            if existing:
                raise ValueError(f"Article is already in the recycle bin: {article_id}")
            connection.execute(
                f"""
                INSERT INTO noosphere_article_trash
                    (article_id, title, url, deleted_at, details_json)
                VALUES ({marker}, {marker}, {marker}, {marker}, {marker})
                """,
                (article_id, title, url, deleted_at, payload),
            )
        return {
            "id": article_id,
            "title": title,
            "url": url,
            "deletedAt": deleted_at,
            "details": details,
        }

    def get(self, article_id: str) -> dict[str, Any] | None:
        self.ensure_schema()
        marker = self._placeholder
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT article_id, title, url, deleted_at, details_json
                FROM noosphere_article_trash
                WHERE article_id = {marker}
                """,
                (article_id,),
            ).fetchone()
        return self._public_record(dict(row)) if row else None

    def list(self) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT article_id, title, url, deleted_at, details_json
                FROM noosphere_article_trash
                ORDER BY deleted_at DESC
                """
            ).fetchall()
        return [self._public_record(dict(row)) for row in rows]

    def remove(self, article_id: str) -> None:
        self.ensure_schema()
        marker = self._placeholder
        with self._connect() as connection:
            connection.execute(
                f"DELETE FROM noosphere_article_trash WHERE article_id = {marker}",
                (article_id,),
            )

    @staticmethod
    def _public_record(row: dict[str, Any]) -> dict[str, Any]:
        try:
            details = json.loads(row.get("details_json") or "{}")
        except json.JSONDecodeError:
            details = {}
        return {
            "id": str(row["article_id"]),
            "title": str(row.get("title") or row["article_id"]),
            "url": str(row.get("url") or ""),
            "deletedAt": str(row["deleted_at"]),
            "details": details if isinstance(details, dict) else {},
        }
