"""Authenticate the HTTP workspace and MCP transport at the same boundary."""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import os
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse

SESSION_COOKIE = "noosphere_session"
SESSION_MAX_AGE = 30 * 24 * 3600

# Paths reachable without credentials so the SPA can load and show its
# in-app login page. API and MCP transports stay protected.
_PUBLIC_EXACT_PATHS = {"/health", "/api/v1/auth/status", "/api/v1/auth/login", "/api/v1/auth/logout"}
_PUBLIC_PREFIXES = ("/app", "/favicon")


def session_signature(token: str) -> str:
    """Derive the cookie value from the access token without storing it."""
    return hmac.new(token.encode(), b"noosphere-web-session", hashlib.sha256).hexdigest()


def local_peer(request: Request) -> bool:
    if not request.client:
        return False
    # TestClient uses a non-IP transport name that cannot arrive over TCP.
    if request.client.host == "testclient":
        return True
    try:
        address = ipaddress.ip_address(request.client.host)
        return address.is_loopback or bool(getattr(address, "ipv4_mapped", None) and address.ipv4_mapped.is_loopback)
    except ValueError:
        return False


def authenticated(request: Request) -> bool:
    expected = os.environ.get("NOOSPHERE_ACCESS_TOKEN", "")
    if not expected:
        return False
    scheme, _, credential = request.headers.get("authorization", "").partition(" ")
    if scheme.casefold() == "basic":
        try:
            credential = base64.b64decode(credential, validate=True).decode().split(":", 1)[1]
        except (ValueError, UnicodeError, IndexError):
            return False
        return hmac.compare_digest(credential.encode(), expected.encode())
    if scheme.casefold() == "bearer":
        return hmac.compare_digest(credential.encode(), expected.encode())
    cookie = request.cookies.get(SESSION_COOKIE, "")
    return bool(cookie) and hmac.compare_digest(cookie.encode(), session_signature(expected).encode())


class AccessControl:
    """Require credentials remotely; reject cross-origin browser requests."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        if path in _PUBLIC_EXACT_PATHS or any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES):
            return await self.app(scope, receive, send)
        request = Request(scope)
        token_configured = bool(os.environ.get("NOOSPHERE_ACCESS_TOKEN"))
        allowed = authenticated(request)
        if not token_configured:
            allowed = local_peer(request) and request.url.hostname in {"localhost", "127.0.0.1", "::1", "testserver"}
        if not allowed:
            # No WWW-Authenticate challenge: the SPA renders its own login page
            # instead of the browser's native Basic Auth dialog.
            response = JSONResponse(
                {"error": "Authentication required. Sign in on the login page with your access token."},
                status_code=401 if token_configured else 403,
                headers={"Cache-Control": "no-store"},
            )
            return await response(scope, receive, send)
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).netloc != request.url.netloc:
            return await JSONResponse({"error": "Cross-origin requests are not allowed"}, status_code=403)(scope, receive, send)
        return await self.app(scope, receive, send)
