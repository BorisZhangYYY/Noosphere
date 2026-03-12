from __future__ import annotations

from typing import Final

USERS_TABLE_NAME: Final[str] = "user_info"
SCHEMA_MIGRATIONS_TABLE_NAME: Final[str] = "schema_migrations"

# ---------------------------------------------------------------------------
# Schema migrations table
# ---------------------------------------------------------------------------

CREATE_SCHEMA_MIGRATIONS_TABLE_SQL: Final[str] = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INT          PRIMARY KEY,
    applied_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
)
"""

# ---------------------------------------------------------------------------
# Migration 1 – create user_info from scratch with ALL columns.
# Only runs on fresh databases where the table does not yet exist.
# Indexes are deliberately omitted here because CREATE INDEX IF NOT EXISTS
# referencing a column that doesn't exist yet (on old DBs) would fail.
# Migration 2 handles both new-column additions AND index creation so that
# indexes are always applied in a single idempotent pass.
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Migration 2 – bring any existing user_info table (old or new) up to date.
#
# Each ALTER TABLE is wrapped in an anonymous DO block so it becomes a
# no-op when the column already exists.  The final CREATE INDEX statements
# use IF NOT EXISTS, so they are safe to run on both fresh and upgraded DBs.
# ---------------------------------------------------------------------------

MIGRATION_2_SQL_PARTS: Final[tuple[str, ...]] = (
    # --- email column -------------------------------------------------------
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
    # --- unique constraint on email ----------------------------------------
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
    # --- is_active column ---------------------------------------------------
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
    # --- email_verified column ----------------------------------------------
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
    # --- last_login_at column -----------------------------------------------
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
    # --- indexes ------------------------------------------------------------
    "CREATE INDEX IF NOT EXISTS idx_user_info_username ON user_info (username)",
    "CREATE INDEX IF NOT EXISTS idx_user_info_email    ON user_info (email)",
)

# ---------------------------------------------------------------------------
# Ordered migrations registry
# Each entry: (version: int, sql_parts: tuple[str, ...])
# Using tuples of individual statements avoids multi-statement parsing issues
# with psycopg v3, which sends each execute() call as a single query.
# ---------------------------------------------------------------------------

MIGRATIONS: Final[tuple[tuple[int, tuple[str, ...]], ...]] = (
    (1, (MIGRATION_1_SQL,)),
    (2, MIGRATION_2_SQL_PARTS),
)

# ---------------------------------------------------------------------------
# Legacy constant – kept for backward-compatibility with any code that still
# imports CREATE_USERS_TABLE_SQL directly.
# ---------------------------------------------------------------------------

CREATE_USERS_TABLE_SQL: Final[str] = MIGRATION_1_SQL
