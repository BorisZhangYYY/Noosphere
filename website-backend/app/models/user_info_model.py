from __future__ import annotations

from typing import Final

USERS_TABLE_NAME: Final[str] = "user_info"

CREATE_USERS_TABLE_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS user_info (
    id BIGSERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""
