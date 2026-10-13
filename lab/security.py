from __future__ import annotations

import logging
import os
import secrets
import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from lab.config import lab_api_auth_enabled, lab_api_max_body_bytes

logger = logging.getLogger(__name__)

_TOKEN: str | None = None
_RATE_BUCKETS: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_POST_PER_MINUTE = 120


def _normalize_token(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if cleaned.lower().startswith("bearer "):
        cleaned = cleaned[7:].strip()
    return cleaned or None


def ensure_lab_api_token() -> str | None:
    """Return the configured token, generating one when auth is enabled and unset."""
    global _TOKEN
    if not lab_api_auth_enabled():
        return None
    if _TOKEN:
        return _TOKEN
    env_token = _normalize_token(os.environ.get("LAB_API_TOKEN"))
    if env_token:
        _TOKEN = env_token
        return _TOKEN
    generated = secrets.token_urlsafe(32)
    _TOKEN = generated
    logger.warning(
        "LAB_API_TOKEN is not set; generated an ephemeral token for this process. "
        "Set LAB_API_TOKEN in the environment for a stable secret.",
    )
    logger.info("Lab API bearer token (keep private): %s", generated)
    return _TOKEN


def lab_api_token() -> str | None:
    if not lab_api_auth_enabled():
        return None
    return ensure_lab_api_token()


def verify_lab_api_token(header_authorization: str | None, x_lab_api_token: str | None) -> None:
    from fastapi import HTTPException

    if not lab_api_auth_enabled():
        return
    expected = lab_api_token()
    if not expected:
        raise HTTPException(status_code=503, detail="Lab API auth is misconfigured")
    provided = _normalize_token(header_authorization) or _normalize_token(x_lab_api_token)
    if provided != expected:
        raise HTTPException(status_code=401, detail="invalid or missing Lab API token")


def lab_auth_dependency():
    from fastapi import Header

    def _dependency(
        authorization: str | None = Header(default=None),
        x_lab_api_token: str | None = Header(default=None, alias="X-Lab-Api-Token"),
    ) -> None:
        verify_lab_api_token(authorization, x_lab_api_token)

    return _dependency


def _client_key(scope: dict[str, Any]) -> str:
    client = scope.get("client")
    if client is None:
        return "unknown"
    host = getattr(client, "host", None)
    return str(host or "unknown")


def _rate_limit_post(client_key: str) -> str | None:
    now = time.monotonic()
    window_start = now - 60.0
    bucket = _RATE_BUCKETS[client_key]
    _RATE_BUCKETS[client_key] = [stamp for stamp in bucket if stamp >= window_start]
    if len(_RATE_BUCKETS[client_key]) >= _RATE_LIMIT_POST_PER_MINUTE:
        return "rate limit exceeded"
    _RATE_BUCKETS[client_key].append(now)
    return None


def _path_requires_auth(method: str, path: str) -> bool:
    if not lab_api_auth_enabled():
        return False
    if method == "OPTIONS":
        return False
    if path == "/health":
        return False
    if path == "/api/auth/status":
        return False
    if method == "GET" and path.startswith("/docs"):
        return False
    if method == "GET" and path.startswith("/openapi"):
        return False
    if method == "POST":
        return True
    if method == "GET" and path.startswith("/artifact"):
        return True
    if method == "GET" and "/download" in path:
        return True
    if method == "GET" and path.startswith("/api/auth/") and path != "/api/auth/status":
        return True
    if path.startswith("/api/risk/"):
        return True
    if path.startswith("/api/infrastructure/"):
        return True
    return False


class LabSecurityMiddleware:
    """Bearer token auth, POST rate limiting, and request body size limits."""

    def __init__(self, app: Callable):
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method") or "GET").upper()
        path = str(scope.get("path") or "")

        if method == "POST":
            rate_detail = _rate_limit_post(_client_key(scope))
            if rate_detail is not None:
                from starlette.responses import JSONResponse

                response = JSONResponse(status_code=429, content={"detail": rate_detail})
                await response(scope, receive, send)
                return

        headers = {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope.get("headers", [])}
        content_length = headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > lab_api_max_body_bytes():
                    from starlette.responses import JSONResponse

                    response = JSONResponse(status_code=413, content={"detail": "request body too large"})
                    await response(scope, receive, send)
                    return
            except ValueError:
                pass

        if _path_requires_auth(method, path):
            from fastapi import HTTPException
            from starlette.responses import JSONResponse

            try:
                verify_lab_api_token(headers.get("authorization"), headers.get("x-lab-api-token"))
            except HTTPException as exc:
                response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


def attach_lab_security(app: Any) -> None:
    ensure_lab_api_token()
    app.add_middleware(LabSecurityMiddleware)
