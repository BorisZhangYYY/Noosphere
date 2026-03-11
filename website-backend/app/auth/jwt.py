from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt


def create_access_token(
    subject: str,
    secret_key: str,
    expires_in_seconds: int = 7 * 24 * 60 * 60,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """Create a JWT access token.

    Args:
        subject: Subject identifier, typically user id or username.
        secret_key: JWT signing secret.
        expires_in_seconds: Token TTL.
        extra_claims: Optional extra claims to embed into token.

    Returns:
        Encoded JWT string.
    """
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in_seconds)).timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    token = jwt.encode(payload, secret_key, algorithm="HS256")
    return str(token)


def decode_token(token: str, secret_key: str) -> Dict[str, Any]:
    """Decode and verify a JWT token.

    Args:
        token: Encoded JWT token.
        secret_key: JWT signing secret.

    Returns:
        Decoded token payload.
    """
    payload: Dict[str, Any] = jwt.decode(token, secret_key, algorithms=["HS256"])
    return payload
