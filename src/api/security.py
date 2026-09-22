"""Authenticate the HTTP workspace and MCP transport at the same boundary."""
from __future__ import annotations

import base64
import hmac
import ipaddress
import os
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse


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
    elif scheme.casefold() != "bearer":
        return False
    return hmac.compare_digest(credential.encode(), expected.encode())


class AccessControl:
    """Require credentials remotely; reject cross-origin browser requests."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") == "/health":
            return await self.app(scope, receive, send)
        request = Request(scope)
        token_configured = bool(os.environ.get("NOOSPHERE_ACCESS_TOKEN"))
        allowed = authenticated(request)
        if not token_configured:
            allowed = local_peer(request) and request.url.hostname in {"localhost", "127.0.0.1", "::1", "testserver"}
        if not allowed:
            response = JSONResponse(
                {"error": "Authentication required. Configure NOOSPHERE_ACCESS_TOKEN and sign in with that token as the password."},
                status_code=401 if token_configured else 403,
                headers={"WWW-Authenticate": 'Basic realm="Noosphere", charset="UTF-8"', "Cache-Control": "no-store"},
            )
            return await response(scope, receive, send)
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).netloc != request.url.netloc:
            return await JSONResponse({"error": "Cross-origin requests are not allowed"}, status_code=403)(scope, receive, send)
        return await self.app(scope, receive, send)
