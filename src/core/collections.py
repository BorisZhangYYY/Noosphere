"""Persistent hierarchical collections for the Noosphere knowledge workspace."""
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


class CollectionStore:
    """Store an arbitrary-depth collection tree and one placement per article."""

    _LEGACY_MIGRATION_KEY = "taxonomy-v1-to-collections-v1"
    _LEGACY_LOCALIZATION_MIGRATION_KEY = "taxonomy-v1-localizations-to-collections-v1"

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
                CREATE TABLE IF NOT EXISTS noosphere_collections (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    parent_id TEXT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS noosphere_collection_states (
                    collection_id TEXT PRIMARY KEY,
                    retired_at TEXT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS noosphere_collection_localizations (
                    collection_id TEXT NOT NULL,
                    locale TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY(collection_id, locale)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS noosphere_article_collections (
                    article_id TEXT PRIMARY KEY,
                    collection_id TEXT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 1,
                    source TEXT NOT NULL DEFAULT 'manual',
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS noosphere_collection_migrations (
                    migration_key TEXT PRIMARY KEY,
                    migrated_at TEXT NOT NULL
                )
                """
            )
            self._migrate_legacy_taxonomy(connection)

    def _table_exists(self, connection, table_name: str) -> bool:
        marker = self._placeholder
        if self._postgres_url:
            row = connection.execute(
                f"""
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = {marker}
                """,
                (table_name,),
            ).fetchone()
        else:
            row = connection.execute(
                f"SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = {marker}",
                (table_name,),
            ).fetchone()
        return row is not None

    def _migrate_legacy_taxonomy(self, connection) -> None:
        marker = self._placeholder
        migrated = connection.execute(
            f"SELECT 1 FROM noosphere_collection_migrations WHERE migration_key = {marker}",
            (self._LEGACY_MIGRATION_KEY,),
        ).fetchone()
        if not migrated and self._table_exists(connection, "noosphere_tags"):
            rows = connection.execute(
                """
                SELECT t.id, t.name, t.description, t.parent_id, t.created_at,
                       state.retired_at
                FROM noosphere_tags t
                LEFT JOIN noosphere_tag_states state ON state.tag_id = t.id
                """
            ).fetchall()
            for row in rows:
                item = dict(row)
                connection.execute(
                    f"""
                    INSERT INTO noosphere_collections
                        (id, name, description, parent_id, created_at)
                    VALUES ({marker}, {marker}, {marker}, {marker}, {marker})
                    ON CONFLICT(id) DO NOTHING
                    """,
                    (
                        item["id"],
                        item["name"],
                        item.get("description") or "",
                        item.get("parent_id"),
                        item.get("created_at") or _now(),
                    ),
                )
                if item.get("retired_at"):
                    connection.execute(
                        f"""
                        INSERT INTO noosphere_collection_states (collection_id, retired_at)
                        VALUES ({marker}, {marker})
                        ON CONFLICT(collection_id) DO UPDATE SET retired_at = excluded.retired_at
                        """,
                        (item["id"], item["retired_at"]),
                    )
        if not migrated and self._table_exists(connection, "noosphere_article_tags"):
            has_details = self._table_exists(
                connection,
                "noosphere_article_classification_details",
            )
            details_join = (
                "LEFT JOIN noosphere_article_classification_details d "
                "ON d.article_id = a.article_id"
                if has_details
                else ""
            )
            confidence_select = "COALESCE(d.confidence, 1)" if has_details else "1"
            source_select = "COALESCE(d.source, 'manual')" if has_details else "'manual'"
            assignments = connection.execute(
                f"""
                SELECT a.article_id, COALESCE(a.subtag_id, a.tag_id) AS collection_id,
                       a.reason, a.updated_at,
                       {confidence_select} AS confidence,
                       {source_select} AS source
                FROM noosphere_article_tags a
                {details_join}
                """
            ).fetchall()
            for row in assignments:
                item = dict(row)
                connection.execute(
                    f"""
                    INSERT INTO noosphere_article_collections
                        (article_id, collection_id, reason, confidence, source, updated_at)
                    VALUES ({marker}, {marker}, {marker}, {marker}, {marker}, {marker})
                    ON CONFLICT(article_id) DO NOTHING
                    """,
                    (
                        item["article_id"],
                        item.get("collection_id"),
                        item.get("reason") or "",
                        item.get("confidence") or 1,
                        item.get("source") or "manual",
                        item.get("updated_at") or _now(),
                    ),
                )
        if not migrated:
            connection.execute(
                f"""
                INSERT INTO noosphere_collection_migrations (migration_key, migrated_at)
                VALUES ({marker}, {marker})
                """,
                (self._LEGACY_MIGRATION_KEY, _now()),
            )
        self._migrate_legacy_localizations(connection)

    def _migrate_legacy_localizations(self, connection) -> None:
        """Preserve legacy locale values, including after the base migration ran."""
        marker = self._placeholder
        migrated = connection.execute(
            f"SELECT 1 FROM noosphere_collection_migrations WHERE migration_key = {marker}",
            (self._LEGACY_LOCALIZATION_MIGRATION_KEY,),
        ).fetchone()
        if migrated:
            return
        if self._table_exists(connection, "noosphere_tags"):
            rows = connection.execute(
                """
                SELECT tag.id, tag.name, tag.description
                FROM noosphere_tags tag
                JOIN noosphere_collections collection ON collection.id = tag.id
                """
            ).fetchall()
            for row in rows:
                item = dict(row)
                connection.execute(
                    f"""
                    INSERT INTO noosphere_collection_localizations
                        (collection_id, locale, name, description)
                    VALUES ({marker}, {marker}, {marker}, {marker})
                    ON CONFLICT(collection_id, locale) DO NOTHING
                    """,
                    (
                        item["id"],
                        "en-US",
                        item["name"],
                        item.get("description") or "",
                    ),
                )
        if self._table_exists(connection, "noosphere_tag_localizations"):
            rows = connection.execute(
                """
                SELECT localization.tag_id, localization.locale,
                       localization.name, localization.description
                FROM noosphere_tag_localizations localization
                JOIN noosphere_collections collection
                  ON collection.id = localization.tag_id
                """
            ).fetchall()
            for row in rows:
                item = dict(row)
                connection.execute(
                    f"""
                    INSERT INTO noosphere_collection_localizations
                        (collection_id, locale, name, description)
                    VALUES ({marker}, {marker}, {marker}, {marker})
                    ON CONFLICT(collection_id, locale) DO UPDATE
                    SET name = excluded.name, description = excluded.description
                    """,
                    (
                        item["tag_id"],
                        item["locale"],
                        item["name"],
                        item.get("description") or "",
                    ),
                )
        connection.execute(
            f"""
            INSERT INTO noosphere_collection_migrations (migration_key, migrated_at)
            VALUES ({marker}, {marker})
            """,
            (self._LEGACY_LOCALIZATION_MIGRATION_KEY, _now()),
        )

    @staticmethod
    def _public_collection(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "name": str(row["name"]),
            "description": str(row.get("description") or ""),
            "parent_id": row.get("parent_id"),
            "retired": bool(row.get("retired_at")),
            "children": [],
        }

    def _all_rows(self, locale: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = [
                dict(row)
                for row in connection.execute(
                    f"""
                    SELECT c.id, c.name, c.description, c.parent_id, c.created_at,
                           state.retired_at,
                           (
                               SELECT COUNT(*)
                               FROM noosphere_article_collections placement
                               WHERE placement.collection_id = c.id
                           ) AS direct_article_count
                    FROM noosphere_collections c
                    LEFT JOIN noosphere_collection_states state
                      ON state.collection_id = c.id
                    ORDER BY c.name COLLATE NOCASE
                    """
                    if not self._postgres_url
                    else f"""
                    SELECT c.id, c.name, c.description, c.parent_id, c.created_at,
                           state.retired_at,
                           (
                               SELECT COUNT(*)
                               FROM noosphere_article_collections placement
                               WHERE placement.collection_id = c.id
                           ) AS direct_article_count
                    FROM noosphere_collections c
                    LEFT JOIN noosphere_collection_states state
                      ON state.collection_id = c.id
                    ORDER BY LOWER(c.name)
                    """,
                ).fetchall()
            ]
            if locale:
                marker = self._placeholder
                localized_rows = connection.execute(
                    f"""
                    SELECT collection_id, name, description
                    FROM noosphere_collection_localizations
                    WHERE locale = {marker}
                    """,
                    (locale,),
                ).fetchall()
                localizations = {
                    str(dict(row)["collection_id"]): dict(row)
                    for row in localized_rows
                }
                for row in rows:
                    localized = localizations.get(str(row["id"]))
                    if localized:
                        row["name"] = localized["name"]
                        row["description"] = localized.get("description") or ""
            return rows

    def list_tree(
        self,
        *,
        include_retired: bool = False,
        locale: str | None = None,
    ) -> list[dict[str, Any]]:
        self.ensure_schema()
        rows = self._all_rows(locale)
        nodes = {
            str(row["id"]): {
                **self._public_collection(row),
                "direct_article_count": int(row.get("direct_article_count") or 0),
                "article_count": int(row.get("direct_article_count") or 0),
            }
            for row in rows
        }
        roots: list[dict[str, Any]] = []
        for row in rows:
            node = nodes[str(row["id"])]
            parent = nodes.get(str(row.get("parent_id") or ""))
            if parent is None:
                roots.append(node)
            else:
                parent["children"].append(node)

        def finalize(node: dict[str, Any], ancestor_retired: bool) -> dict[str, Any] | None:
            hidden = ancestor_retired or bool(node["retired"])
            visible_children = []
            total = int(node["direct_article_count"])
            for child in node["children"]:
                finalized = finalize(child, hidden)
                if finalized is not None:
                    visible_children.append(finalized)
                    total += int(finalized["article_count"])
            node["children"] = visible_children
            node["article_count"] = total
            if hidden and not include_retired:
                return None
            return node

        result = [
            finalized
            for root in roots
            if (finalized := finalize(root, False)) is not None
        ]
        return sorted(result, key=lambda item: item["name"].casefold())

    def get_collection(
        self,
        collection_id: str,
        *,
        include_retired: bool = False,
        locale: str | None = None,
    ) -> dict[str, Any] | None:
        self.ensure_schema()
        marker = self._placeholder
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT c.id, c.name, c.description, c.parent_id, c.created_at,
                       state.retired_at
                FROM noosphere_collections c
                LEFT JOIN noosphere_collection_states state
                  ON state.collection_id = c.id
                WHERE c.id = {marker}
                """,
                (collection_id,),
            ).fetchone()
        if row is None:
            return None
        item = self._public_collection(dict(row))
        if locale:
            localized = self._localized_value(collection_id, locale)
            if localized:
                item["name"] = localized["name"]
                item["description"] = localized["description"]
        if item["retired"] and not include_retired:
            return None
        item["path"] = self.get_path(
            collection_id,
            include_retired=include_retired,
            locale=locale,
        )
        return item

    def _localized_value(self, collection_id: str, locale: str) -> dict[str, str] | None:
        marker = self._placeholder
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT name, description
                FROM noosphere_collection_localizations
                WHERE collection_id = {marker} AND locale = {marker}
                """,
                (collection_id, locale),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        return {
            "name": str(item["name"]),
            "description": str(item.get("description") or ""),
        }

    def get_path(
        self,
        collection_id: str,
        *,
        include_retired: bool = False,
        locale: str | None = None,
    ) -> list[dict[str, str]]:
        self.ensure_schema()
        rows = {str(row["id"]): row for row in self._all_rows(locale)}
        path: list[dict[str, str]] = []
        visited: set[str] = set()
        current_id: str | None = collection_id
        while current_id:
            if current_id in visited:
                raise ValueError("Collection hierarchy contains a cycle")
            visited.add(current_id)
            row = rows.get(current_id)
            if row is None:
                raise ValueError(f"Collection not found: {current_id}")
            if row.get("retired_at") and not include_retired:
                return []
            path.append({"id": current_id, "name": str(row["name"])})
            current_id = str(row.get("parent_id") or "") or None
        path.reverse()
        return path

    def get_collection_by_path(
        self,
        names: list[str],
        *,
        include_retired: bool = False,
    ) -> dict[str, Any] | None:
        """Resolve an exact, case-insensitive collection path by sibling names."""
        self.ensure_schema()
        normalized_names = [str(name).strip() for name in names]
        if not normalized_names or any(not name for name in normalized_names):
            raise ValueError("Collection path must contain at least one non-empty name")
        rows = self._all_rows()
        parent_id: str | None = None
        collection_id: str | None = None
        for name in normalized_names:
            matches = [
                row
                for row in rows
                if row.get("parent_id") == parent_id
                and str(row["name"]).casefold() == name.casefold()
            ]
            if not matches:
                return None
            row = matches[0]
            if row.get("retired_at") and not include_retired:
                return None
            collection_id = str(row["id"])
            parent_id = collection_id
        if collection_id is None:
            return None
        return self.get_collection(collection_id, include_retired=include_retired)

    def create_collection(
        self,
        *,
        name: str,
        description: str = "",
        parent_id: str | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_schema()
        name = name.strip()
        description = description.strip()
        if not name:
            raise ValueError("Collection name is required")
        marker = self._placeholder
        with self._connect() as connection:
            if parent_id:
                parent = connection.execute(
                    f"""
                    SELECT c.id, state.retired_at
                    FROM noosphere_collections c
                    LEFT JOIN noosphere_collection_states state
                      ON state.collection_id = c.id
                    WHERE c.id = {marker}
                    """,
                    (parent_id,),
                ).fetchone()
                if parent is None:
                    raise ValueError(f"Parent collection not found: {parent_id}")
                if dict(parent).get("retired_at"):
                    raise ValueError("Cannot create a child inside a deleted collection")
            self._assert_unique_name(
                connection,
                name=name,
                parent_id=parent_id,
            )
            collection_id = uuid.uuid4().hex
            connection.execute(
                f"""
                INSERT INTO noosphere_collections
                    (id, name, description, parent_id, created_at)
                VALUES ({marker}, {marker}, {marker}, {marker}, {marker})
                """,
                (collection_id, name, description, parent_id, _now()),
            )
            if locale:
                connection.execute(
                    f"""
                    INSERT INTO noosphere_collection_localizations
                        (collection_id, locale, name, description)
                    VALUES ({marker}, {marker}, {marker}, {marker})
                    """,
                    (collection_id, locale, name, description),
                )
        collection = self.get_collection(
            collection_id,
            include_retired=True,
            locale=locale,
        )
        if collection is None:
            raise RuntimeError("Collection was not persisted")
        return collection

    def update_collection(
        self,
        collection_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        retired: bool | None = None,
        locale: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_schema()
        marker = self._placeholder
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT id, name, description, parent_id
                FROM noosphere_collections
                WHERE id = {marker}
                """,
                (collection_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Collection not found: {collection_id}")
            current = dict(row)
            localized_data: dict[str, Any] = {}
            if locale:
                localized = connection.execute(
                    f"""
                    SELECT name, description
                    FROM noosphere_collection_localizations
                    WHERE collection_id = {marker} AND locale = {marker}
                    """,
                    (collection_id, locale),
                ).fetchone()
                localized_data = dict(localized) if localized else {}
            next_name = str(
                name
                if name is not None
                else localized_data.get("name") or current["name"]
            ).strip()
            next_description = str(
                description
                if description is not None
                else localized_data.get("description") or current.get("description") or ""
            ).strip()
            if not next_name:
                raise ValueError("Collection name is required")
            if name is not None:
                if locale:
                    self._assert_unique_localized_name(
                        connection,
                        name=next_name,
                        parent_id=current.get("parent_id"),
                        locale=locale,
                        exclude_id=collection_id,
                    )
                else:
                    self._assert_unique_name(
                        connection,
                        name=next_name,
                        parent_id=current.get("parent_id"),
                        exclude_id=collection_id,
                    )
            if locale and (name is not None or description is not None):
                connection.execute(
                    f"""
                    INSERT INTO noosphere_collection_localizations
                        (collection_id, locale, name, description)
                    VALUES ({marker}, {marker}, {marker}, {marker})
                    ON CONFLICT(collection_id, locale) DO UPDATE
                    SET name = excluded.name, description = excluded.description
                    """,
                    (collection_id, locale, next_name, next_description),
                )
            elif not locale:
                connection.execute(
                    f"""
                    UPDATE noosphere_collections
                    SET name = {marker}, description = {marker}
                    WHERE id = {marker}
                    """,
                    (next_name, next_description, collection_id),
                )
            if retired is not None:
                affected = self._descendant_ids(connection, collection_id)
                affected.add(collection_id)
                retired_at = _now() if retired else None
                for affected_id in affected:
                    connection.execute(
                        f"""
                        INSERT INTO noosphere_collection_states
                            (collection_id, retired_at)
                        VALUES ({marker}, {marker})
                        ON CONFLICT(collection_id) DO UPDATE
                            SET retired_at = excluded.retired_at
                        """,
                        (affected_id, retired_at),
                    )
        collection = self.get_collection(
            collection_id,
            include_retired=True,
            locale=locale,
        )
        if collection is None:
            raise RuntimeError("Collection update was not persisted")
        return collection

    def _descendant_ids(self, connection, collection_id: str) -> set[str]:
        marker = self._placeholder
        descendants: set[str] = set()
        frontier = [collection_id]
        while frontier:
            parent_id = frontier.pop()
            child_ids = [
                str(dict(row)["id"])
                for row in connection.execute(
                    f"SELECT id FROM noosphere_collections WHERE parent_id = {marker}",
                    (parent_id,),
                ).fetchall()
            ]
            for child_id in child_ids:
                if child_id not in descendants:
                    descendants.add(child_id)
                    frontier.append(child_id)
        return descendants

    def _assert_unique_name(
        self,
        connection,
        *,
        name: str,
        parent_id: str | None,
        exclude_id: str | None = None,
    ) -> None:
        rows = connection.execute(
            "SELECT id, name, parent_id FROM noosphere_collections"
        ).fetchall()
        for row in rows:
            item = dict(row)
            if exclude_id and item["id"] == exclude_id:
                continue
            if item.get("parent_id") == parent_id and str(item["name"]).casefold() == name.casefold():
                raise ValueError(f"A collection named '{name}' already exists at this level")

    def _assert_unique_localized_name(
        self,
        connection,
        *,
        name: str,
        parent_id: str | None,
        locale: str,
        exclude_id: str | None = None,
    ) -> None:
        marker = self._placeholder
        rows = connection.execute(
            f"""
            SELECT collection.id,
                   collection.parent_id,
                   COALESCE(localization.name, collection.name) AS displayed_name
            FROM noosphere_collections collection
            LEFT JOIN noosphere_collection_localizations localization
              ON localization.collection_id = collection.id
             AND localization.locale = {marker}
            """,
            (locale,),
        ).fetchall()
        for row in rows:
            item = dict(row)
            if exclude_id and item["id"] == exclude_id:
                continue
            if (
                item.get("parent_id") == parent_id
                and str(item["displayed_name"]).casefold() == name.casefold()
            ):
                raise ValueError(f"A collection named '{name}' already exists at this level")

    def assign_article(
        self,
        article_id: str,
        *,
        collection_id: str | None,
        reason: str = "",
        confidence: float = 1.0,
        source: str = "manual",
    ) -> dict[str, Any]:
        self.ensure_schema()
        if not 0 <= confidence <= 1:
            raise ValueError("Collection confidence must be between 0 and 1")
        marker = self._placeholder
        if collection_id:
            collection = self.get_collection(collection_id)
            if collection is None:
                raise ValueError(f"Active collection not found: {collection_id}")
        with self._connect() as connection:
            connection.execute(
                f"""
                INSERT INTO noosphere_article_collections
                    (article_id, collection_id, reason, confidence, source, updated_at)
                VALUES ({marker}, {marker}, {marker}, {marker}, {marker}, {marker})
                ON CONFLICT(article_id) DO UPDATE SET
                    collection_id = excluded.collection_id,
                    reason = excluded.reason,
                    confidence = excluded.confidence,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (
                    article_id,
                    collection_id,
                    reason.strip(),
                    confidence,
                    source.strip() or "manual",
                    _now(),
                ),
            )
        assignment = self.get_assignment(article_id)
        if assignment is None:
            raise RuntimeError("Article placement was not persisted")
        return assignment

    def get_assignment(
        self,
        article_id: str,
        *,
        locale: str | None = None,
    ) -> dict[str, Any] | None:
        self.ensure_schema()
        marker = self._placeholder
        with self._connect() as connection:
            row = connection.execute(
                f"""
                SELECT article_id, collection_id, reason, confidence, source, updated_at
                FROM noosphere_article_collections
                WHERE article_id = {marker}
                """,
                (article_id,),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        collection_id = str(item.get("collection_id") or "") or None
        path = self.get_path(collection_id, locale=locale) if collection_id else []
        if collection_id and not path:
            collection_id = None
        return {
            "article_id": article_id,
            "collection_id": collection_id,
            "collection_name": path[-1]["name"] if path else None,
            "collection_path": path,
            "reason": str(item.get("reason") or ""),
            "confidence": float(item.get("confidence") or 0),
            "source": str(item.get("source") or "manual"),
            "updated_at": item.get("updated_at"),
        }

    def get_search_terms(
        self,
        article_id: str,
        *,
        locale: str | None = None,
    ) -> list[str]:
        assignment = self.get_assignment(article_id, locale=locale)
        if not assignment:
            return []
        return [str(item["name"]) for item in assignment["collection_path"]]

    def delete_assignment(self, article_id: str) -> None:
        self.ensure_schema()
        marker = self._placeholder
        with self._connect() as connection:
            connection.execute(
                f"DELETE FROM noosphere_article_collections WHERE article_id = {marker}",
                (article_id,),
            )

    def classification_candidates(
        self,
        *,
        locale: str | None = None,
    ) -> list[dict[str, str]]:
        candidates: list[dict[str, str]] = []

        def walk(nodes: list[dict[str, Any]], path: list[str]) -> None:
            for node in nodes:
                current_path = [*path, node["name"]]
                candidates.append({
                    "id": node["id"],
                    "path": " / ".join(current_path),
                    "description": node["description"],
                })
                walk(node["children"], current_path)

        walk(self.list_tree(locale=locale), [])
        return candidates


def _extract_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Collection response did not contain a JSON object")
    payload = json.loads(text[start:end + 1])
    if not isinstance(payload, dict):
        raise ValueError("Collection response must be a JSON object")
    return payload


async def place_reviewed_article(
    article_id: str,
    reviewed_path: Path,
    locale: str = "en-US",
) -> dict[str, Any]:
    """Place a reviewed article in an existing collection or at the root."""
    from src.core.paths import resolve_project_path
    from src.core.review.prompt_metadata import parse_prompt_file
    from src.integrations.ai_client import AIClient, resolve_ai_settings

    config = load_config()
    store = CollectionStore()
    candidates = store.classification_candidates(locale=locale)
    if not candidates:
        return store.assign_article(
            article_id,
            collection_id=None,
            confidence=0,
            reason="No collections are configured",
            source="ai",
        )
    system_prompt = parse_prompt_file(
        resolve_project_path(config.pipeline.classification_prompt_path)
    ).body
    markdown = reviewed_path.read_text(encoding="utf-8")
    from src.core.telemetry import reset_event_sink, suspend_event_sink

    token = suspend_event_sink()
    try:
        response = await AIClient(resolve_ai_settings(config)).generate_text(
            system_prompt,
            "Existing collections:\n"
            + json.dumps(candidates, ensure_ascii=False)
            + "\n\nReviewed article:\n"
            + markdown,
        )
    finally:
        reset_event_sink(token)
    payload = _extract_json_object(response.text)
    collection_id = str(payload.get("collection_id") or "").strip() or None
    reason = str(payload.get("reason") or "").strip()
    try:
        confidence = float(payload.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(confidence, 1.0))
    if not collection_id or confidence < 0.6:
        return store.assign_article(
            article_id,
            collection_id=None,
            confidence=confidence,
            reason=reason or "No existing collection matched with sufficient confidence",
            source="ai",
        )
    try:
        assignment = store.assign_article(
            article_id,
            collection_id=collection_id,
            confidence=confidence,
            reason=reason,
            source="ai",
        )
    except ValueError as exc:
        assignment = store.assign_article(
            article_id,
            collection_id=None,
            confidence=confidence,
            reason=f"AI returned an unknown collection: {exc}",
            source="ai",
        )
    return assignment
