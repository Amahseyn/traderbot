from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lab.auth_service import (
    api_keys_create,
    api_keys_list,
    auth_status,
    fetch_profile,
    login_session,
)
from traderbot.nobitex.client import NobitexClientError


def register_auth_routes(app, _get_connection: Callable | None = None) -> None:
    from fastapi import HTTPException

    @app.get("/api/auth/status")
    def api_auth_status():
        return auth_status()

    @app.get("/api/auth/profile")
    def api_auth_profile():
        try:
            return fetch_profile()
        except NobitexClientError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/auth/login")
    def api_auth_login(body: dict[str, Any]):
        username = body.get("username")
        password = body.get("password")
        if not username or not password:
            raise HTTPException(status_code=400, detail="username and password required")
        try:
            return login_session(
                username=str(username),
                password=str(password),
                totp=body.get("totp"),
                remember=bool(body.get("remember")),
                write_env=bool(body.get("write_env", True)),
            )
        except NobitexClientError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/auth/api-keys")
    def api_auth_api_keys_list():
        try:
            return api_keys_list()
        except (NobitexClientError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/auth/api-keys")
    def api_auth_api_keys_create(body: dict[str, Any]):
        totp = body.get("totp")
        if not totp:
            raise HTTPException(status_code=400, detail="totp required")
        try:
            return api_keys_create(
                name=str(body.get("name") or "traderbot-lab"),
                totp=str(totp),
                permissions=str(body.get("permissions") or "READ"),
                description=str(body.get("description") or "Created via Traderbot Lab"),
                write_env=bool(body.get("write_env", True)),
            )
        except NobitexClientError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
