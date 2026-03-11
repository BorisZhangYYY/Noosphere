from __future__ import annotations

import os
from typing import Any, Dict, Tuple

from flask import Flask, Response, jsonify

from conf.config import Config
from app.common_func.api import create_api

app = Flask(__name__)
app.config.from_object(Config())
create_api(app)

try:
    import psycopg
except Exception:  # pragma: no cover
    psycopg = None  # type: ignore[assignment]


def create_app() -> Flask:
    """Create and configure the Flask application.

    Returns:
        A configured Flask application instance.
    """
    return app

@app.get("/")
def index() -> Response:
    """Return basic application information."""
    payload: Dict[str, Any] = {
        "app": "hot-knowledge-backend",
        "debug": app.config.get("DEBUG", False),
        "database_dsn": app.config.get("DATABASE_DSN", ""),
    }
    return jsonify(payload)


@app.get("/healthz")
def healthz() -> Response:
    """Return application health status."""
    payload: Dict[str, str] = {"status": "ok"}
    return jsonify(payload)

def _db_connect() -> "psycopg.Connection[Any]":  # type: ignore[name-defined]
    """Create a new database connection using the configured DSN."""
    if psycopg is None:
        raise RuntimeError("psycopg is not installed")
    dsn = str(app.config.get("DATABASE_DSN", ""))
    return psycopg.connect(dsn, connect_timeout=3)

@app.get("/db/health")
def db_health() -> Response:
    """Perform a simple PostgreSQL health check using SELECT 1."""
    try:
        with _db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                row: Tuple[int] = cur.fetchone()  # type: ignore[assignment]
        status: Dict[str, Any] = {"database": "ok", "result": int(row[0])}
        return jsonify(status)
    except Exception as exc:  # pragma: no cover
        status = {"database": "error", "detail": str(exc)}
        return jsonify(status), 503

if __name__ == "__main__":
    host = os.getenv("FLASK_RUN_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_RUN_PORT", "15000"))
    app.run(host=host, port=port, debug=app.config.get("DEBUG", False))
