"""Keep every test away from the developer's configured article library."""
import json
import uuid
import pytest
from src.core.config.config import clear_config_cache


def pytest_addoption(parser):
    parser.addoption("--isolated-postgres-dsn", default=None, help="Disposable PostgreSQL DSN; each test gets its own temporary schema")


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch, tmp_path, request):
    home = tmp_path / "default-runtime"
    home.mkdir()
    config = home / "config.json"
    config.write_text(json.dumps({"output_dir": str(home / "articles"), "checkpoint": {"backend": "sqlite"}, "ai": {"provider": "test"}, "ai_providers": {"test": {"api_format": "openai_chat", "model": "test-model", "api_base": "http://127.0.0.1:9/v1", "api_key": "test-only"}}}))
    monkeypatch.setenv("NOOSPHERE_HOME", str(home))
    monkeypatch.setenv("NOOSPHERE_CONFIG", str(config))
    for name in ("NOOSPHERE_ACCESS_TOKEN", "DATABASE_URL", "NOOSPHERE_OUTPUT_DIR", "NOOSPHERE_CHECKPOINT_BACKEND"):
        monkeypatch.delenv(name, raising=False)
    postgres_dsn = request.config.getoption("--isolated-postgres-dsn")
    schema = None
    if postgres_dsn:
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import make_conninfo

        schema = "noosphere_test_" + uuid.uuid4().hex
        with psycopg.connect(postgres_dsn) as connection:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        monkeypatch.setenv("DATABASE_URL", make_conninfo(postgres_dsn, options=f"-c search_path={schema}"))
        monkeypatch.setenv("NOOSPHERE_CHECKPOINT_BACKEND", "postgres")
    clear_config_cache()
    try:
        yield
    finally:
        clear_config_cache()
        if schema:
            with psycopg.connect(postgres_dsn) as connection:
                connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
