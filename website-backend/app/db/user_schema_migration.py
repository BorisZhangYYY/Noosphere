from __future__ import annotations

from typing import Final

CREATE_SCHEMA_MIGRATIONS_TABLE_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INT          PRIMARY KEY,
    applied_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
)
"""

MIGRATION_1_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS user_info (
    id               BIGSERIAL    PRIMARY KEY,
    username         TEXT         UNIQUE NOT NULL,
    password_hash    TEXT         NOT NULL,
    email            TEXT         UNIQUE,
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    email_verified   BOOLEAN      NOT NULL DEFAULT FALSE,
    last_login_at    TIMESTAMPTZ,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
)
"""

MIGRATION_2_SQL_PARTS: Final[tuple[str, ...]] = (
    """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE  table_name = 'user_info' AND column_name = 'email'
    ) THEN
        ALTER TABLE user_info ADD COLUMN email TEXT;
    END IF;
END$$
""",
    """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE  conrelid = 'user_info'::regclass
        AND    conname  = 'user_info_email_key'
    ) THEN
        ALTER TABLE user_info ADD CONSTRAINT user_info_email_key UNIQUE (email);
    END IF;
END$$
""",
    """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE  table_name = 'user_info' AND column_name = 'is_active'
    ) THEN
        ALTER TABLE user_info ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE;
    END IF;
END$$
""",
    """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE  table_name = 'user_info' AND column_name = 'email_verified'
    ) THEN
        ALTER TABLE user_info ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
END$$
""",
    """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE  table_name = 'user_info' AND column_name = 'last_login_at'
    ) THEN
        ALTER TABLE user_info ADD COLUMN last_login_at TIMESTAMPTZ;
    END IF;
END$$
""",
    "CREATE INDEX IF NOT EXISTS idx_user_info_username ON user_info (username)",
    "CREATE INDEX IF NOT EXISTS idx_user_info_email    ON user_info (email)",
)

MIGRATIONS: Final[tuple[tuple[int, tuple[str, ...]], ...]] = (
    (1, (MIGRATION_1_SQL,)),
    (2, MIGRATION_2_SQL_PARTS),
)

CREATE_USERS_TABLE_SQL: Final[str] = MIGRATION_1_SQL
