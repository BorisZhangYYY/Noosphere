from __future__ import annotations

from typing import Any

from flask import current_app

try:
    import psycopg
except Exception:  # pragma: no cover
    psycopg = None  # type: ignore[assignment]


def get_db_connection() -> "psycopg.Connection[Any]":  # type: ignore[name-defined]
    """Create a PostgreSQL connection using app config DATABASE_DSN."""
    if psycopg is None:
        raise RuntimeError("psycopg is not installed")
    dsn = str(current_app.config.get("DATABASE_DSN", ""))
    return psycopg.connect(dsn, connect_timeout=3)
