from __future__ import annotations

from typing import Iterable, List

from app.db.connection import get_db_connection
from app.db.user_schema_migration import (
    CREATE_SCHEMA_MIGRATIONS_TABLE_SQL,
    CREATE_USERS_TABLE_SQL,
    MIGRATIONS,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ensure_migrations_table(conn: "psycopg.Connection") -> None:  # type: ignore[name-defined]
    """Create the schema_migrations tracking table if it does not exist."""
    with conn.cursor() as cur:
        cur.execute(CREATE_SCHEMA_MIGRATIONS_TABLE_SQL)


def _get_applied_versions(conn: "psycopg.Connection") -> List[int]:  # type: ignore[name-defined]
    """Return a list of already-applied migration version numbers."""
    with conn.cursor() as cur:
        cur.execute("SELECT version FROM schema_migrations ORDER BY version")
        rows = cur.fetchall()
    return [int(row[0]) for row in rows]


def _record_migration(conn: "psycopg.Connection", version: int) -> None:  # type: ignore[name-defined]
    """Insert a version record into schema_migrations."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO schema_migrations (version) VALUES (%s) ON CONFLICT DO NOTHING",
            (version,),
        )


def _apply_parts(conn: "psycopg.Connection", parts: "tuple[str, ...]") -> None:  # type: ignore[name-defined]
    """Execute each SQL part individually using the provided connection.

    psycopg v3 sends each ``execute()`` call as a single query, so
    multi-statement strings must be split into individual parts before
    calling this function.
    """
    with conn.cursor() as cur:
        for part in parts:
            sql = part.strip()
            if sql:
                cur.execute(sql)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_migrations() -> None:
    """Apply all pending versioned migrations in order.

    Algorithm
    ---------
    1. Open a single connection for the entire migration run.
    2. Ensure the ``schema_migrations`` tracking table exists.
    3. Fetch already-applied version numbers.
    4. For each migration ``(version, sql_parts)`` in ``MIGRATIONS``, skip it
       if its version is already recorded; otherwise execute every SQL part in
       order and record the version — all within the same autocommit-style
       transaction that psycopg v3 commits on context-manager exit.
    """
    with get_db_connection() as conn:
        _ensure_migrations_table(conn)
        applied = set(_get_applied_versions(conn))

        for version, sql_parts in MIGRATIONS:
            if version in applied:
                continue
            _apply_parts(conn, sql_parts)
            _record_migration(conn, version)


def ensure_users_table_exists() -> None:
    """Compatibility shim: create user_info table if it does not exist.

    Prefer calling :func:`run_migrations` instead, which handles the full
    versioned schema.  This function is kept so that existing call-sites
    continue to work without modification.
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_USERS_TABLE_SQL)


def init_schema(ddls: "Iterable[str] | None" = None) -> None:  # type: ignore[name-defined]
    """Initialize DB schema.

    When *ddls* is ``None`` the versioned migration runner is used.
    When an explicit iterable of DDL strings is provided each one is applied
    directly (legacy behaviour, useful in tests).

    Args:
        ddls: Optional iterable of raw DDL strings.  Pass ``None`` to run the
              full versioned migration suite.
    """
    if ddls is None:
        run_migrations()
        return

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for sql in ddls:
                cur.execute(sql)
