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
                CREATE TABLE IF NOT EXISTS noosphere_tag_localizations (
                    tag_id TEXT NOT NULL,
                    locale TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    aliases_json TEXT NOT NULL DEFAULT '[]',
                    PRIMARY KEY(tag_id, locale)
                )
                """
            )
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

    def list_tree(self, locale: str = "en-US") -> list[dict[str, Any]]:
        self.ensure_schema()
        from src.core.localization import normalize_language
        locale = normalize_language(locale)
        marker = self._placeholder
        with self._connect() as connection:
            rows = [dict(row) for row in connection.execute(
                f"""
                SELECT t.id, COALESCE(l.name, t.name) AS name,
                       COALESCE(l.description, t.description) AS description,
                       COALESCE(l.aliases_json, '[]') AS aliases_json,
                       t.parent_id
                FROM noosphere_tags t
                LEFT JOIN noosphere_tag_localizations l ON l.tag_id = t.id AND l.locale = {marker}
                ORDER BY COALESCE(l.name, t.name)
                """,
                (locale,),
            ).fetchall()]
        roots: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not row["parent_id"]:
                roots[row["id"]] = self._public_tag(row)
        for row in rows:
            parent_id = row["parent_id"]
            if parent_id and parent_id in roots:
                roots[parent_id]["children"].append(self._public_tag(row))
        return list(roots.values())

    @staticmethod
    def _public_tag(row: dict[str, Any]) -> dict[str, Any]:
        try:
            aliases = json.loads(row.get("aliases_json") or "[]")
        except json.JSONDecodeError:
            aliases = []
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row.get("description") or "",
            "aliases": aliases if isinstance(aliases, list) else [],
            "parent_id": row.get("parent_id"),
            "children": [],
        }

    def get_assignment(self, article_id: str, locale: str = "en-US") -> dict[str, Any] | None:
        self.ensure_schema()
        from src.core.localization import normalize_language
        locale = normalize_language(locale)
        marker = self._placeholder
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT a.article_id, a.reason,
                       t.id AS tag_id, COALESCE(tl.name, t.name) AS tag_name,
                       s.id AS subtag_id, COALESCE(sl.name, s.name) AS subtag_name
                FROM noosphere_article_tags a
                JOIN noosphere_tags t ON t.id = a.tag_id
                LEFT JOIN noosphere_tags s ON s.id = a.subtag_id
                LEFT JOIN noosphere_tag_localizations tl ON tl.tag_id = t.id AND tl.locale = {marker}
                LEFT JOIN noosphere_tag_localizations sl ON sl.tag_id = s.id AND sl.locale = {marker}
                WHERE a.article_id = {marker}
                """,
                (locale, locale, article_id),
            ).fetchone()
        return dict(row) if row else None

    def get_search_terms(self, article_id: str) -> list[str]:
        """Return names and aliases from every locale for the assigned tag path."""
        self.ensure_schema()
        marker = self._placeholder
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT l.name, l.aliases_json
                FROM noosphere_article_tags a
                JOIN noosphere_tag_localizations l ON l.tag_id = a.tag_id OR l.tag_id = a.subtag_id
                WHERE a.article_id = {marker}
                """,
                (article_id,),
            ).fetchall()
        terms: set[str] = set()
        for row in rows:
            data = dict(row)
            if data.get("name"):
                terms.add(str(data["name"]))
            try:
                aliases = json.loads(data.get("aliases_json") or "[]")
            except json.JSONDecodeError:
                aliases = []
            terms.update(str(alias) for alias in aliases if alias)
        return sorted(terms, key=str.casefold)

    def assign(
        self,
        article_id: str,
        *,
        tag_name: str,
        tag_description: str = "",
        subtag_name: str | None = None,
        subtag_description: str = "",
        reason: str = "",
        locale: str = "en-US",
        tag_localizations: dict[str, dict[str, Any]] | None = None,
        subtag_localizations: dict[str, dict[str, Any]] | None = None,
        tag_id: str | None = None,
        subtag_id: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_schema()
        tag_name = tag_name.strip()
        subtag_name = subtag_name.strip() if subtag_name else None
        if not tag_name:
            raise ValueError("A top-level tag is required")
        with self._connect() as connection:
            tag_id = self._upsert_tag(connection, tag_name, tag_description.strip(), None, tag_localizations, preferred_id=tag_id)
            subtag_id = self._upsert_tag(connection, subtag_name, subtag_description.strip(), tag_id, subtag_localizations, preferred_id=subtag_id) if subtag_name else None
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
        assignment = self.get_assignment(article_id, locale)
        if assignment is None:
            raise RuntimeError("Tag assignment was not persisted")
        return assignment

    def _upsert_tag(
        self,
        connection,
        name: str,
        description: str,
        parent_id: str | None,
        localizations: dict[str, dict[str, Any]] | None = None,
        *,
        preferred_id: str | None = None,
    ) -> str:
        marker = self._placeholder
        row = None
        if preferred_id:
            row = connection.execute("SELECT id, description FROM noosphere_tags WHERE id = " + marker, (preferred_id,)).fetchone()
        if row is None:
            candidates = {name.casefold()}
            for localized in (localizations or {}).values():
                localized_name = str(localized.get("name") or "").strip()
                candidates.update(item.casefold() for item in [localized_name, *(localized.get("aliases") or [])] if str(item).strip())
            localization_rows = connection.execute(
                "SELECT tag_id, name, aliases_json FROM noosphere_tag_localizations"
            ).fetchall()
            matched_ids: set[str] = set()
            for localization_row in localization_rows:
                data = dict(localization_row)
                aliases = json.loads(data.get("aliases_json") or "[]")
                known = {str(data.get("name") or "").casefold(), *(str(alias).casefold() for alias in aliases)}
                if candidates & known:
                    matched_ids.add(str(data["tag_id"]))
            if matched_ids:
                placeholders = ",".join(marker for _ in matched_ids)
                parent_clause = "parent_id IS NULL" if parent_id is None else f"parent_id = {marker}"
                params = (*matched_ids,) if parent_id is None else (*matched_ids, parent_id)
                row = connection.execute(
                    f"SELECT id, description FROM noosphere_tags WHERE id IN ({placeholders}) AND {parent_clause} LIMIT 1",
                    params,
                ).fetchone()
        if row is None and parent_id is None:
            row = connection.execute(
                "SELECT id, description FROM noosphere_tags WHERE parent_id IS NULL AND name = " + marker,
                (name,),
            ).fetchone()
        elif row is None:
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
            tag_id = str(row_data["id"])
            self._upsert_localizations(connection, tag_id, localizations or {})
            return tag_id
        tag_id = uuid.uuid4().hex
        connection.execute(
            f"INSERT INTO noosphere_tags (id, name, description, parent_id, created_at) VALUES ({marker}, {marker}, {marker}, {marker}, {marker})",
            (tag_id, name, description, parent_id, _now()),
        )
        fallback_localizations = localizations or {"en-US": {"name": name, "description": description, "aliases": []}, "zh-CN": {"name": name, "description": description, "aliases": []}}
        self._upsert_localizations(connection, tag_id, fallback_localizations)
        return tag_id

    def _upsert_localizations(self, connection, tag_id: str, localizations: dict[str, dict[str, Any]]) -> None:
        marker = self._placeholder
        for locale, value in localizations.items():
            name = str(value.get("name") or "").strip()
            if not name:
                continue
            description = str(value.get("description") or "").strip()
            aliases = sorted({str(alias).strip() for alias in value.get("aliases") or [] if str(alias).strip() and str(alias).casefold() != name.casefold()})
            existing = connection.execute(
                f"SELECT name, description, aliases_json FROM noosphere_tag_localizations WHERE tag_id = {marker} AND locale = {marker}",
                (tag_id, locale),
            ).fetchone()
            if existing:
                current = dict(existing)
                current_name = str(current.get("name") or name)
                current_description = str(current.get("description") or "")
                try:
                    current_aliases = json.loads(current.get("aliases_json") or "[]")
                except json.JSONDecodeError:
                    current_aliases = []
                if name.casefold() != current_name.casefold():
                    aliases.append(name)
                aliases = sorted({*current_aliases, *aliases}, key=str.casefold)
                connection.execute(
                    f"UPDATE noosphere_tag_localizations SET name={marker}, description={marker}, aliases_json={marker} WHERE tag_id={marker} AND locale={marker}",
                    (current_name, current_description or description, json.dumps(aliases, ensure_ascii=False), tag_id, locale),
                )
            else:
                connection.execute(
                    f"INSERT INTO noosphere_tag_localizations (tag_id, locale, name, description, aliases_json) VALUES ({marker}, {marker}, {marker}, {marker}, {marker})",
                    (tag_id, locale, name, description, json.dumps(aliases, ensure_ascii=False)),
                )


def _extract_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Classification response did not contain a JSON object")
    payload = json.loads(text[start:end + 1])
    if not isinstance(payload, dict):
        raise ValueError("Classification response must be a JSON object")
    return payload


async def classify_reviewed_article(article_id: str, reviewed_path: Path, locale: str = "en-US") -> dict[str, Any]:
    """Classify a reviewed article against the existing taxonomy and persist it."""
    from src.core.review.prompt_metadata import parse_prompt_file
    from src.core.paths import resolve_project_path
    from src.integrations.ai_client import AIClient, resolve_ai_settings

    config = load_config()
    store = CatalogStore()
    taxonomy = store.list_tree(locale)
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
    if not isinstance(tag, dict):
        raise ValueError("Classification response is missing tag")
    if subtag is not None and not isinstance(subtag, dict):
        raise ValueError("Classification subtag must be an object or null")
    def translations(value: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
        if not value:
            return {}
        raw = value.get("translations") or value.get("localizations") or {}
        return raw if isinstance(raw, dict) else {}

    tag_translations = translations(tag)
    subtag_translations = translations(subtag) if subtag else {}
    tag_name = str(tag.get("name") or (tag_translations.get(locale) or {}).get("name") or (next(iter(tag_translations.values()), {})).get("name") or "").strip()
    subtag_name = str(subtag.get("name") or (subtag_translations.get(locale) or {}).get("name") or (next(iter(subtag_translations.values()), {})).get("name") or "").strip() if subtag else None
    if not tag_name:
        raise ValueError("Classification response is missing a tag name")
    return store.assign(
        article_id,
        tag_name=tag_name,
        tag_description=str(tag.get("description") or ""),
        subtag_name=subtag_name,
        subtag_description=str(subtag.get("description") or "") if subtag else "",
        reason=str(payload.get("reason") or ""),
        locale=locale,
        tag_localizations=tag_translations,
        subtag_localizations=subtag_translations,
        tag_id=str(tag.get("id") or "") or None,
        subtag_id=str(subtag.get("id") or "") or None if subtag else None,
    )
