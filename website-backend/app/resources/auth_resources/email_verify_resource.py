from __future__ import annotations

import random
import time
from typing import Any, Dict, Tuple

from flask import request
from flask_restful import Resource

from app.auth.validation import validate_email

# ---------------------------------------------------------------------------
# In-memory OTP store
# ---------------------------------------------------------------------------
# Structure: { email: {"code": str, "expires_at": float} }
# expires_at is a Unix timestamp (time.time() + 600 seconds).
# This is a simple dev-mode store — no Redis, no persistence.
# ---------------------------------------------------------------------------

otp_store: Dict[str, Dict[str, Any]] = {}

_OTP_TTL_SECONDS: int = 600  # 10 minutes


def _generate_otp() -> str:
    """Generate a zero-padded 6-digit OTP code.

    Returns:
        A string of exactly 6 digits, e.g. ``"042817"``.
    """
    return f"{random.randint(0, 999999):06d}"


def _store_otp(email: str, code: str) -> None:
    """Write an OTP entry into the in-memory store.

    Args:
        email: The target email address (used as the dict key).
        code:  The 6-digit OTP string to store.
    """
    otp_store[email] = {
        "code": code,
        "expires_at": time.time() + _OTP_TTL_SECONDS,
    }


def is_otp_valid(email: str, code: str) -> bool:
    """Check whether the supplied OTP code is correct and not expired.

    Args:
        email: The email address to look up.
        code:  The OTP code supplied by the caller.

    Returns:
        ``True`` if the code matches and has not yet expired, ``False``
        otherwise.
    """
    entry = otp_store.get(email)
    if entry is None:
        return False
    if time.time() > entry["expires_at"]:
        # Lazily evict expired entry
        otp_store.pop(email, None)
        return False
    return entry["code"] == code


class EmailVerifyResource(Resource):
    """Email verification / OTP dispatch resource.

    POST /api/auth/email_verifying
    --------------------------------
    Accepts a JSON body::

        {"email": "user@example.com"}

    Behaviour
    ---------
    - Validates the email format.
    - Generates a 6-digit OTP and stores it in :data:`otp_store` with a
      10-minute TTL.
    - In production you would dispatch the code via an email provider; for
      this dev build the code is returned directly in the response body under
      the key ``"code"`` alongside ``"detail": "dev_mode"``.

    Returns
    -------
    200  ``{"message": "ok", "code": "<otp>", "detail": "dev_mode"}``
    400  ``{"message": "validation_error", "errors": {"email": "<reason>"}}``
    """

    def post(self) -> Tuple[Dict[str, Any], int]:
        """Generate and (in dev mode) return a 6-digit OTP for the given email.

        Returns:
            A tuple of (json_body, http_status_code).
        """
        payload: Any = request.get_json(silent=True)

        if not isinstance(payload, dict):
            return {"message": "validation_error", "errors": {"payload": "JSON object is required"}}, 400

        email_raw: Any = payload.get("email")
        if not isinstance(email_raw, str) or not email_raw.strip():
            return {
                "message": "validation_error",
                "errors": {"email": "This field is required"},
            }, 400

        email: str = email_raw.strip().lower()

        valid, email_err = validate_email(email)
        if not valid:
            return {
                "message": "validation_error",
                "errors": {"email": email_err},
            }, 400

        code: str = _generate_otp()
        _store_otp(email, code)

        # ------------------------------------------------------------------
        # Dev mode: return the OTP directly since there is no email server.
        # In production, replace this block with an actual send and return:
        #   {"message": "ok", "detail": "verification code sent"}
        # ------------------------------------------------------------------
        return {
            "message": "ok",
            "code": code,
            "detail": "dev_mode",
        }, 200
