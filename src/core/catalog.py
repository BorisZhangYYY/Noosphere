"""Persistent two-level article taxonomy for the web knowledge workspace."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.core.config.config import load_config
from src.core.paths import runtime_home


def _now() -> str:
    return datetime.now(UTC).isoformat()


class CatalogStore:
    """Store tags in PostgreSQL in Docker and SQLite during local development."""

    def __init__(self) -> None:
        config = load_config()
        self._postgres_url = (
            config.checkpoint.effective_postgres_connection_string()
            if config.checkpoint.is_postgres
            else None
        )
        self._sqlite_path = runtime_home() / "catalog.sqlite3"

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
                CREATE TABLE IF NOT EXISTS noosphere_tags (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    parent_id TEXT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(parent_id, name)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS noosphere_article_tags (
                    article_id TEXT PRIMARY KEY,
                    tag_id TEXT NOT NULL,
                    subtag_id TEXT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                )
                """
            )

    def list_tree(self) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._connect() as connection:
            rows = [dict(row) for row in connection.execute(
                "SELECT id, name, description, parent_id FROM noosphere_tags ORDER BY name"
            ).fetchall()]
        roots: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not row["parent_id"]:
                roots[row["id"]] = {**row, "children": []}
        for row in rows:
            parent_id = row["parent_id"]
            if parent_id and parent_id in roots:
                roots[parent_id]["children"].append({**row, "children": []})
        return list(roots.values())

    def get_assignment(self, article_id: str) -> dict[str, Any] | None:
        self.ensure_schema()
        marker = self._placeholder
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT a.article_id, a.reason,
                       t.id AS tag_id, t.name AS tag_name,
                       s.id AS subtag_id, s.name AS subtag_name
                FROM noosphere_article_tags a
                JOIN noosphere_tags t ON t.id = a.tag_id
                LEFT JOIN noosphere_tags s ON s.id = a.subtag_id
                WHERE a.article_id = {marker}
                """,
                (article_id,),
            ).fetchone()
        return dict(row) if row else None

    def assign(
        self,
        article_id: str,
        *,
        tag_name: str,
        tag_description: str = "",
        subtag_name: str | None = None,
        subtag_description: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        self.ensure_schema()
        tag_name = tag_name.strip()
        subtag_name = subtag_name.strip() if subtag_name else None
        if not tag_name:
            raise ValueError("A top-level tag is required")
        with self._connect() as connection:
            tag_id = self._upsert_tag(connection, tag_name, tag_description.strip(), None)
            subtag_id = (
                self._upsert_tag(connection, subtag_name, subtag_description.strip(), tag_id)
                if subtag_name
                else None
            )
            marker = self._placeholder
            existing = connection.execute(
                f"SELECT article_id FROM noosphere_article_tags WHERE article_id = {marker}",
                (article_id,),
            ).fetchone()
            values = (tag_id, subtag_id, reason.strip(), _now(), article_id)
            if existing:
                connection.execute(
                    f"UPDATE noosphere_article_tags SET tag_id={marker}, subtag_id={marker}, reason={marker}, updated_at={marker} WHERE article_id={marker}",
                    values,
                )
            else:
                connection.execute(
                    f"INSERT INTO noosphere_article_tags (tag_id, subtag_id, reason, updated_at, article_id) VALUES ({marker}, {marker}, {marker}, {marker}, {marker})",
                    values,
                )
        assignment = self.get_assignment(article_id)
        if assignment is None:
            raise RuntimeError("Tag assignment was not persisted")
        return assignment

    def _upsert_tag(self, connection, name: str, description: str, parent_id: str | None) -> str:
        marker = self._placeholder
        if parent_id is None:
            row = connection.execute(
                "SELECT id, description FROM noosphere_tags WHERE parent_id IS NULL AND name = " + marker,
                (name,),
            ).fetchone()
        else:
            row = connection.execute(
                f"SELECT id, description FROM noosphere_tags WHERE parent_id = {marker} AND name = {marker}",
                (parent_id, name),
            ).fetchone()
        if row:
            row_data = dict(row)
            if description and not row_data.get("description"):
                connection.execute(
                    f"UPDATE noosphere_tags SET description = {marker} WHERE id = {marker}",
                    (description, row_data["id"]),
                )
            return str(row_data["id"])
        tag_id = uuid.uuid4().hex
        connection.execute(
            f"INSERT INTO noosphere_tags (id, name, description, parent_id, created_at) VALUES ({marker}, {marker}, {marker}, {marker}, {marker})",
            (tag_id, name, description, parent_id, _now()),
        )
        return tag_id


def _extract_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Classification response did not contain a JSON object")
    payload = json.loads(text[start:end + 1])
    if not isinstance(payload, dict):
        raise ValueError("Classification response must be a JSON object")
    return payload


async def classify_reviewed_article(article_id: str, reviewed_path: Path) -> dict[str, Any]:
    """Classify a reviewed article against the existing taxonomy and persist it."""
    from src.core.review.prompt_metadata import parse_prompt_file
    from src.core.paths import resolve_project_path
    from src.integrations.ai_client import AIClient, resolve_ai_settings

    config = load_config()
    store = CatalogStore()
    taxonomy = store.list_tree()
    system_prompt = parse_prompt_file(
        resolve_project_path(config.pipeline.classification_prompt_path)
    ).body
    markdown = reviewed_path.read_text(encoding="utf-8")
    from src.core.telemetry import reset_event_sink, suspend_event_sink

    token = suspend_event_sink()
    try:
        response = await AIClient(resolve_ai_settings(config)).generate_text(
            system_prompt,
            "Existing taxonomy:\n"
            + json.dumps(taxonomy, ensure_ascii=False)
            + "\n\nReviewed article:\n"
            + markdown,
        )
    finally:
        reset_event_sink(token)
    payload = _extract_json_object(response.text)
    tag = payload.get("tag")
    subtag = payload.get("subtag")
    if not isinstance(tag, dict) or not str(tag.get("name") or "").strip():
        raise ValueError("Classification response is missing tag.name")
    if subtag is not None and not isinstance(subtag, dict):
        raise ValueError("Classification subtag must be an object or null")
    return store.assign(
        article_id,
        tag_name=str(tag["name"]),
        tag_description=str(tag.get("description") or ""),
        subtag_name=str(subtag.get("name") or "") if subtag else None,
        subtag_description=str(subtag.get("description") or "") if subtag else "",
        reason=str(payload.get("reason") or ""),
    )
