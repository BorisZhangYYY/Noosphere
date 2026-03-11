from __future__ import annotations

from typing import Any, Dict, Tuple

from flask import current_app, request
from flask_restful import Resource

from app.auth.jwt import create_access_token
from app.auth.passwords import hash_password
from app.auth.validation import require_json_fields
from app.db.connection import get_db_connection
from app.db.migration import ensure_users_table_exists
from app.models.user_info_model import USERS_TABLE_NAME


class UserLoginResource(Resource):
    """User register resource."""

    def post(self) -> Tuple[Dict[str, Any], int]:
        """Register a new user.

        Returns:
            A tuple of (json_body, http_status_code).
        """
        payload = request.get_json(silent=True)
        ok, errors = require_json_fields(payload, ("username", "password"))
        if not ok:
            return {"message": "validation_error", "errors": errors}, 400

        username = str(payload["username"]).strip()
        password = str(payload["password"])

        ensure_users_table_exists()
        password_hash = hash_password(password)

        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"INSERT INTO {USERS_TABLE_NAME} (username, password_hash) VALUES (%s, %s) RETURNING id",
                        (username, password_hash),
                    )
                    row = cur.fetchone()
            user_id = int(row[0]) if row else 0
        except Exception as exc:
            msg = str(exc).lower()
            if "duplicate" in msg or "unique" in msg:
                return {"message": "username_already_exists"}, 409
            return {"message": "database_error", "detail": str(exc)}, 500

        secret_key = str(current_app.config.get("SECRET_KEY", ""))
        token = create_access_token(subject=str(user_id), secret_key=secret_key, extra_claims={"username": username})
        return {"message": "ok", "user_id": user_id, "username": username, "access_token": token}, 201
