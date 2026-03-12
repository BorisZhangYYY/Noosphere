from __future__ import annotations

from typing import Any, Dict, Set, Tuple

from flask import request
from flask_restful import Resource

from app.auth.middleware import require_auth

# ---------------------------------------------------------------------------
# In-memory token blacklist
# ---------------------------------------------------------------------------
# A simple set of raw JWT strings that have been explicitly invalidated via
# logout.  On server restart the set is cleared — that is acceptable for a
# v0.5 dev build where there is no Redis / persistent store yet.
#
# The require_auth middleware does NOT currently consult this blacklist
# automatically; the check is intentionally kept here in the logout resource
# so that the blacklist concern stays co-located and can be extracted to a
# shared auth layer once a proper token store (e.g. Redis) is available.
# ---------------------------------------------------------------------------

token_blacklist: Set[str] = set()


def is_token_blacklisted(token: str) -> bool:
    """Return ``True`` if *token* has been blacklisted by a previous logout.

    Args:
        token: The raw JWT string to check.

    Returns:
        ``True`` when the token is in :data:`token_blacklist`.
    """
    return token in token_blacklist


class LogoutResource(Resource):
    """User logout resource.

    POST /api/auth/logout
    ---------------------
    Requires a valid ``Authorization: Bearer <token>`` header (enforced by
    the :func:`~app.auth.middleware.require_auth` decorator).

    Behaviour
    ---------
    - Extracts the raw JWT from the ``Authorization`` header.
    - Adds it to the module-level :data:`token_blacklist` set so subsequent
      requests carrying the same token can be rejected.
    - Returns a success response immediately; the token is considered
      invalidated from this point onward.

    Returns
    -------
    200  ``{"message": "ok", "detail": "logged_out"}``
    401  Missing / invalid / expired token (handled by ``require_auth``).
    """

    @require_auth
    def post(self) -> Tuple[Dict[str, Any], int]:
        """Blacklist the caller's JWT and confirm logout.

        Returns:
            A tuple of (json_body, http_status_code).
        """
        # require_auth has already validated the token at this point, so we
        # can safely extract the raw string from the header without
        # re-checking it.
        auth_header: str = request.headers.get("Authorization", "")
        # Header format guaranteed by require_auth: "Bearer <token>"
        parts = auth_header.split()
        token: str = parts[1] if len(parts) == 2 else ""

        if token:
            token_blacklist.add(token)

        return {"message": "ok", "detail": "logged_out"}, 200
