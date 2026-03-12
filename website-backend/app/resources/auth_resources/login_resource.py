from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Tuple

from flask import current_app, request
from flask_restful import Resource

from app.auth.jwt import create_access_token
from app.auth.passwords import verify_password
from app.auth.validation import require_json_fields
from app.db.connection import get_db_connection
from app.models.user_info_model import USERS_TABLE_NAME

# ---------------------------------------------------------------------------
# Threshold: if last_login_at is NULL (first login) or older than 7 days,
# flag the response so the client can prompt for email verification.
# ---------------------------------------------------------------------------
_EMAIL_VERIFY_THRESHOLD_DAYS: int = 7


class LoginResource(Resource):
    """User login resource.

    POST /api/auth/login
    --------------------
    Accepts a JSON body::

        {"username": "...", "password": "..."}

    Behaviour
    ---------
    - Looks up the user by username.
    - Verifies the supplied password against the stored hash.
    - Determines whether email verification should be prompted:
        * First ever login (``last_login_at IS NULL``), **or**
        * Last login was more than 7 days ago.
    - Updates ``last_login_at = NOW()`` unconditionally on successful auth.
    - Issues a signed JWT access token.

    Returns
    -------
    200  Success::

            {
                "message": "ok",
                "user_id": <int>,
                "username": <str>,
                "access_token": <str>,
                "needs_email_verify": <bool>
            }

    400  Missing / non-string required fields.
    401  Wrong username or password.
    500  Unexpected database error.
    """

    def post(self) -> Tuple[Dict[str, Any], int]:
        """Authenticate a user and return a JWT access token.

        Returns:
            A tuple of (json_body, http_status_code).
        """
        payload: Any = request.get_json(silent=True)

        # ------------------------------------------------------------------
        # 1. Presence check
        # ------------------------------------------------------------------
        ok, errors = require_json_fields(payload, ("username", "password"))
        if not ok:
            return {"message": "validation_error", "errors": errors}, 400

        username: str = str(payload["username"]).strip()
        password: str = str(payload["password"])

        # ------------------------------------------------------------------
        # 2. Fetch user record
        # ------------------------------------------------------------------
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        SELECT id, password_hash, last_login_at
                        FROM   {USERS_TABLE_NAME}
                        WHERE  username = %s
                        """,
                        (username,),
                    )
                    row = cur.fetchone()
        except Exception as exc:
            return {"message": "database_error", "detail": str(exc)}, 500

        if row is None:
            # User not found — return same message as wrong password to
            # avoid username enumeration.
            return {"message": "invalid_credentials"}, 401

        user_id: int = int(row[0])
        password_hash: str = str(row[1])
        last_login_at: datetime | None = row[2]  # TIMESTAMPTZ → datetime | None

        # ------------------------------------------------------------------
        # 3. Verify password
        # ------------------------------------------------------------------
        if not verify_password(password, password_hash):
            return {"message": "invalid_credentials"}, 401

        # ------------------------------------------------------------------
        # 4. Determine whether email verification should be prompted
        # ------------------------------------------------------------------
        needs_email_verify: bool
        if last_login_at is None:
            # First login ever
            needs_email_verify = True
        else:
            # Ensure offset-aware comparison
            if last_login_at.tzinfo is None:
                last_login_at = last_login_at.replace(tzinfo=timezone.utc)
            cutoff = datetime.now(timezone.utc) - timedelta(days=_EMAIL_VERIFY_THRESHOLD_DAYS)
            needs_email_verify = last_login_at < cutoff

        # ------------------------------------------------------------------
        # 5. Update last_login_at
        # ------------------------------------------------------------------
        try:
            with get_db_connection() as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute(
                            f"""
                            UPDATE {USERS_TABLE_NAME}
                            SET    last_login_at = NOW()
                            WHERE  id = %s
                            """,
                            (user_id,),
                        )
        except Exception as exc:
            return {"message": "database_error", "detail": str(exc)}, 500

        # ------------------------------------------------------------------
        # 6. Issue JWT
        # ------------------------------------------------------------------
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
                "needs_email_verify": needs_email_verify,
            },
            200,
        )
