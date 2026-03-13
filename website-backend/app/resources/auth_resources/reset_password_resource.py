from __future__ import annotations

from typing import Any, Dict, Tuple

from flask import request
from flask_restful import Resource

from app.auth.passwords import hash_password, verify_password
from app.auth.validation import validate_email, validate_password
from app.common_func.validation import require_json_fields
from app.db.connection import get_db_connection
from app.db.user_info_model import USERS_TABLE_NAME
from app.resources.auth_resources.email_verify_resource import is_otp_valid, otp_store


class ResetPasswordResource(Resource):
    """Password reset resource.

    POST /api/auth/reset_success
    ----------------------------
    Accepts a JSON body::

        {
            "email":        "user@example.com",
            "otp_code":     "123456",
            "new_password": "NewPass1"
        }

    Behaviour
    ---------
    1. Validates all three fields are present and non-empty.
    2. Validates ``email`` format.
    3. Validates the OTP against the in-memory :data:`otp_store` (must be
       correct and not expired).
    4. Validates ``new_password`` strength rules (>=8 chars, >=1 upper,
       >=1 lower, >=1 digit).
    5. Looks up the user by email; returns 404 when no account is found.
    6. Verifies the new password is **different** from the current one.
    7. Updates ``password_hash`` in the database inside an explicit
       transaction.
    8. Clears the OTP entry from :data:`otp_store`.

    Returns
    -------
    200  ``{"message": "ok", "detail": "password_reset_success"}``
    400  Validation error (missing fields, bad email, weak password, same
         password, invalid / expired OTP).
    404  No account registered with that email.
    500  Unexpected database error.
    """

    def post(self) -> Tuple[Dict[str, Any], int]:
        """Reset a user's password after OTP verification.

        Returns:
            A tuple of (json_body, http_status_code).
        """
        payload: Any = request.get_json(silent=True)

        # ------------------------------------------------------------------
        # 1. Payload structure check
        # ------------------------------------------------------------------
        ok, errors = require_json_fields(payload, ("email", "otp_code", "new_password"))
        if not ok:
            return {"message": "validation_error", "errors": errors}, 400

        email: str = str(payload["email"]).strip().lower()
        otp_code: str = str(payload["otp_code"]).strip()
        new_password: str = str(payload["new_password"])

        # ------------------------------------------------------------------
        # 3. Email format validation
        # ------------------------------------------------------------------
        valid_email, email_err = validate_email(email)
        if not valid_email:
            return {
                "message": "validation_error",
                "errors": {"email": email_err},
            }, 400

        # ------------------------------------------------------------------
        # 4. OTP validation (must come before password checks to avoid
        #    leaking whether the account exists via error ordering)
        # ------------------------------------------------------------------
        if not is_otp_valid(email, otp_code):
            return {
                "message": "validation_error",
                "errors": {"otp_code": "Invalid or expired verification code"},
            }, 400

        # ------------------------------------------------------------------
        # 5. New password strength validation
        # ------------------------------------------------------------------
        valid_password, password_err = validate_password(new_password)
        if not valid_password:
            return {
                "message": "validation_error",
                "errors": {"new_password": password_err},
            }, 400

        # ------------------------------------------------------------------
        # 6. Fetch the user record by email
        # ------------------------------------------------------------------
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        SELECT id, password_hash
                        FROM   {USERS_TABLE_NAME}
                        WHERE  email = %s
                        """,
                        (email,),
                    )
                    row = cur.fetchone()
        except Exception as exc:
            return {"message": "database_error", "detail": str(exc)}, 500

        if row is None:
            return {
                "message": "not_found",
                "detail": "No account is associated with that email address",
            }, 404

        user_id: int = int(row[0])
        current_password_hash: str = str(row[1])

        # ------------------------------------------------------------------
        # 7. Ensure the new password differs from the existing one
        # ------------------------------------------------------------------
        if verify_password(new_password, current_password_hash):
            return {
                "message": "validation_error",
                "errors": {
                    "new_password": "New password must be different from the current password"
                },
            }, 400

        # ------------------------------------------------------------------
        # 8. Persist the new password hash inside an explicit transaction
        # ------------------------------------------------------------------
        new_password_hash: str = hash_password(new_password)

        try:
            with get_db_connection() as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute(
                            f"""
                            UPDATE {USERS_TABLE_NAME}
                            SET    password_hash = %s
                            WHERE  id = %s
                            """,
                            (new_password_hash, user_id),
                        )
        except Exception as exc:
            return {"message": "database_error", "detail": str(exc)}, 500

        # ------------------------------------------------------------------
        # 9. Invalidate the OTP so it cannot be reused
        # ------------------------------------------------------------------
        otp_store.pop(email, None)

        return {"message": "ok", "detail": "password_reset_success"}, 200
