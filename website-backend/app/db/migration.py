from __future__ import annotations

from typing import Iterable

from app.db.connection import get_db_connection
from app.models.user_info_model import CREATE_USERS_TABLE_SQL


def _apply_ddl(sql: str) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)


def ensure_users_table_exists() -> None:
    """Create user_info table if it does not exist."""
    _apply_ddl(CREATE_USERS_TABLE_SQL)


def init_schema(ddls: Iterable[str] | None = None) -> None:
    """Initialize DB schema by applying registered DDLs.

    Args:
        ddls: Optional iterable of DDL strings to apply. If None, use defaults.
    """
    registry = list(ddls) if ddls is not None else [
        CREATE_USERS_TABLE_SQL,
    ]
    for ddl in registry:
        _apply_ddl(ddl)
