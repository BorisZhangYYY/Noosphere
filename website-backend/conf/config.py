from __future__ import annotations

from typing import Final

from .load_global_conf import get_conf_bool, get_conf_int, get_conf_str, build_postgres_dsn


class Config:
    """Flask application configuration."""

    DEBUG: bool = get_conf_bool("flask", "debug", "FLASK_DEBUG", False)
    TESTING: bool = False
    SECRET_KEY: str = get_conf_str("flask", "secret_key", "SECRET_KEY", "dev-secret-change-me")
    JSON_SORT_KEYS: bool = get_conf_bool("flask", "json_sort_keys", "FLASK_JSON_SORT_KEYS", False)

    POSTGRES_USER: Final[str] = get_conf_str("postgres", "user", "POSTGRES_USER", "boriszhang")
    POSTGRES_PASSWORD: Final[str] = get_conf_str("postgres", "password", "POSTGRES_PASSWORD", "")
    POSTGRES_HOST: Final[str] = get_conf_str("postgres", "host", "POSTGRES_HOST", "localhost")
    POSTGRES_PORT: Final[int] = get_conf_int("postgres", "port", "POSTGRES_PORT", 5432)
    POSTGRES_DB: Final[str] = get_conf_str("postgres", "db", "POSTGRES_DB", "hot_knowledge")

    DATABASE_DSN: str = build_postgres_dsn(
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        db=POSTGRES_DB,
    )
