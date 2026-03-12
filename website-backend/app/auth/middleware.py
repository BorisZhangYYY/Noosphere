from __future__ import annotations

import functools
from typing import Any, Callable, Dict, Tuple, TypeVar

from flask import current_app, g, request
from flask_restful import Resource

from app.auth.jwt import decode_token

F = TypeVar("F", bound=Callable[..., Any])

_UNAUTHORIZED: Tuple[Dict[str, str], int] = ({"message": "unauthorized"}, 401)


def require_auth(fn: F) -> F:
    """Decorator that enforces JWT Bearer authentication on a resource method.

    Usage
    -----
    Apply to any Flask-RESTful resource method (``get``, ``post``, etc.):

    .. code-block:: python

        class MyResource(Resource):
            @require_auth
            def post(self) -> Tuple[Dict, int]:
                user = g.current_user  # {"user_id": ..., "username": ...}
                ...

    Behaviour
    ---------
    - Expects an ``Authorization: Bearer <token>`` header.
    - Decodes and verifies the token using :func:`app.auth.jwt.decode_token`
      with ``current_app.config["SECRET_KEY"]``.
    - On success, stores the parsed identity in ``flask.g.current_user`` as::

          {"user_id": str, "username": str}

      and calls the wrapped function normally.
    - On any failure (missing header, wrong scheme, expired token, bad
      signature, missing claims), returns ``{"message": "unauthorized"}``
      with HTTP 401 without calling the wrapped function.

    Args:
        fn: The resource method to protect.

    Returns:
        The wrapped method with authentication enforcement applied.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        auth_header: str | None = request.headers.get("Authorization")

        if not auth_header:
            return _UNAUTHORIZED

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return _UNAUTHORIZED

        token: str = parts[1]
        secret_key: str = str(current_app.config.get("SECRET_KEY", ""))

        try:
            payload: Dict[str, Any] = decode_token(token, secret_key)
        except Exception:
            return _UNAUTHORIZED

        user_id: Any = payload.get("sub")
        username: Any = payload.get("username")

        if user_id is None or username is None:
            return _UNAUTHORIZED

        g.current_user = {
            "user_id": str(user_id),
            "username": str(username),
        }

        return fn(*args, **kwargs)

    return wrapper  # type: ignore[return-value]
