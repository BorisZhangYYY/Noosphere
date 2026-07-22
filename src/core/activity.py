"""Persistent, append-only article operation history."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Any

from src.core.config.config import load_config
from src.core.paths import runtime_home


class ArticleActivityStore:
    """Record capture, review, and upload operations without coupling them to manifests."""

    def __init__(self) -> None:
        config = load_config()
        self._postgres_url = config.checkpoint.effective_postgres_connection_string() if config.checkpoint.is_postgres else None
        self._sqlite_path = runtime_home() / "activity.sqlite3"

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
                CREATE TABLE IF NOT EXISTS noosphere_article_events (
                    id TEXT PRIMARY KEY,
                    article_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS noosphere_article_events_article_idx ON noosphere_article_events(article_id, created_at)"
            )

    def record(self, article_id: str, event_type: str, **details: Any) -> None:
        if not article_id:
            return
        self.ensure_schema()
        marker = self._placeholder
        with self._connect() as connection:
            connection.execute(
                f"INSERT INTO noosphere_article_events (id, article_id, event_type, created_at, details_json) VALUES ({marker}, {marker}, {marker}, {marker}, {marker})",
                (uuid.uuid4().hex, article_id, event_type, datetime.now(UTC).isoformat(), json.dumps(details, ensure_ascii=False)),
            )

    def backfill_workspace(self, article_id: str, manifest: dict[str, Any], review: dict[str, Any]) -> None:
        """Create one deterministic baseline event for operations predating this store."""
        article = manifest.get("article") or {}
        candidates = [
            ("capture", article.get("captured_at"), {"migrated": True}),
            ("review", review.get("completed_at") or review.get("updated_at"), {"migrated": True}) if review.get("status") == "reviewed" else None,
            ("upload", (manifest.get("uploaded") or {}).get("updated_at"), {"migrated": True, "target": (manifest.get("uploaded") or {}).get("platform")}) if manifest.get("uploaded") else None,
        ]
        self.ensure_schema()
        marker = self._placeholder
        with self._connect() as connection:
            for candidate in candidates:
                if candidate is None:
                    continue
                event_type, created_at, details = candidate
                event_id = f"{article_id}:legacy:{event_type}"
                exists = connection.execute(
                    f"SELECT id FROM noosphere_article_events WHERE id = {marker}", (event_id,)
                ).fetchone()
                if exists:
                    continue
                has_event = connection.execute(
                    f"SELECT id FROM noosphere_article_events WHERE article_id = {marker} AND event_type = {marker} LIMIT 1",
                    (article_id, event_type),
                ).fetchone()
                if has_event:
                    continue
                connection.execute(
                    f"INSERT INTO noosphere_article_events (id, article_id, event_type, created_at, details_json) VALUES ({marker}, {marker}, {marker}, {marker}, {marker})",
                    (event_id, article_id, event_type, str(created_at or datetime.now(UTC).isoformat()), json.dumps(details, ensure_ascii=False)),
                )

    def summary(self, article_id: str, *, limit: int = 20) -> dict[str, Any]:
        self.ensure_schema()
        marker = self._placeholder
        with self._connect() as connection:
            rows = [dict(row) for row in connection.execute(
                f"SELECT id, event_type, created_at, details_json FROM noosphere_article_events WHERE article_id = {marker} ORDER BY created_at DESC",
                (article_id,),
            ).fetchall()]
        counts = {"capture": 0, "review": 0, "upload": 0}
        events: list[dict[str, Any]] = []
        for row in rows:
            event_type = str(row["event_type"])
            if event_type in counts:
                counts[event_type] += 1
            if len(events) < limit:
                try:
                    details = json.loads(row.get("details_json") or "{}")
                except json.JSONDecodeError:
                    details = {}
                events.append({"id": row["id"], "type": event_type, "at": row["created_at"], "details": details})
        return {
            "captureCount": counts["capture"],
            "reviewCount": counts["review"],
            "rereviewCount": max(0, counts["review"] - 1),
            "uploadCount": counts["upload"],
            "events": events,
        }
