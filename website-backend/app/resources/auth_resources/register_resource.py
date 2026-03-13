from __future__ import annotations

from typing import Any, Dict, Tuple

import psycopg.errors
from flask import current_app, request
from flask_restful import Resource

from app.auth.jwt import create_access_token
from app.auth.passwords import hash_password
from app.auth.validation import validate_email, validate_password, validate_username
from app.common_func.validation import require_json_fields
from app.db.connection import get_db_connection
from app.db.migration import run_migrations
from app.db.user_info_model import USERS_TABLE_NAME


class RegisterResource(Resource):
    """User registration resource.

    POST /api/auth/register
    -----------------------
    Accepts a JSON body with the following fields:

    Required:
        username (str): 3-30 chars, alphanumeric + underscores, starts with a letter.
        password (str): min 8 chars, >=1 uppercase, >=1 lowercase, >=1 digit.
        email (str): valid email address, used for password recovery.

    Returns 201 on success with a JWT access token.
    Returns 400 on validation errors.
    Returns 409 when the username or email already exists.
    Returns 500 on unexpected database errors.
    """

    def post(self) -> Tuple[Dict[str, Any], int]:
        """Register a new user.

        Returns:
            A tuple of (json_body, http_status_code).
        """
        payload: Any = request.get_json(silent=True)

        ok, errors = require_json_fields(payload, ("username", "password", "email"))
        if not ok:
            return {"message": "validation_error", "errors": errors}, 400

        assert isinstance(payload, dict)
        username: str = str(payload["username"]).strip()
        password: str = str(payload["password"])
        email: str = str(payload["email"]).strip()

        valid_username, username_err = validate_username(username)
        if not valid_username:
            return {"message": "validation_error", "errors": {"username": username_err}}, 400

        valid_password, password_err = validate_password(password)
        if not valid_password:
            return {"message": "validation_error", "errors": {"password": password_err}}, 400

        valid_email, email_err = validate_email(email)
        if not valid_email:
            return {"message": "validation_error", "errors": {"email": email_err}}, 400

        run_migrations()
        password_hash: str = hash_password(password)

        try:
            with get_db_connection() as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute(
                            f"""
                            INSERT INTO {USERS_TABLE_NAME}
                                (username, password_hash, email)
                            VALUES
                                (%s, %s, %s)
                            RETURNING id
                            """,
                            (username, password_hash, email),
                        )
                        row = cur.fetchone()
            user_id: int = int(row[0]) if row else 0
        except psycopg.errors.UniqueViolation as exc:
            detail: str = str(exc).lower()
            if "email" in detail:
                return {"message": "email_already_exists"}, 409
            return {"message": "username_already_exists"}, 409
        except Exception as exc:
            return {"message": "database_error", "detail": str(exc)}, 500

        secret_key: str = str(current_app.config.get("SECRET_KEY", ""))
        token: str = create_access_token(
            subject=str(user_id),
            secret_key=secret_key,
            extra_claims={"username": username},
        )

        return (
            {
                "message": "ok",
                "user_id": user_id,
                "username": username,
                "access_token": token,
            },
            201,
        )
