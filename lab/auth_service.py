from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from auth.apikeys import create_api_key, list_api_keys, redact_apikey_response
from auth.envfile import load_env_file, upsert_env_vars
from auth.login import login_v2
from auth.session import normalize_totp, token_from_env
from traderbot.nobitex.client import NobitexClient
from traderbot.nobitex.profile import nobitex_keys_configured


def auth_status() -> dict[str, bool]:
    load_env_file()
    token = os.environ.get("NOBITEX_AUTH_TOKEN", "").strip()
    return {
        "api_keys_configured": nobitex_keys_configured(),
        "auth_token_configured": bool(token),
    }


def fetch_profile() -> dict[str, Any]:
    load_env_file()
    return NobitexClient.from_env().request("GET", "/users/profile")


def login_session(
    *,
    username: str,
    password: str,
    totp: str | None = None,
    remember: bool = False,
    write_env: bool = False,
    env_file: Path | None = None,
) -> dict[str, Any]:
    load_env_file()
    normalized_totp = normalize_totp(totp) if totp else None
    result = login_v2(
        username=username.strip(),
        password=password,
        totp=normalized_totp,
        remember=remember,
    )
    token = result.get("key")
    if not token:
        return {"ok": False, "result": result}
    if write_env:
        upsert_env_vars(env_file or Path(".env"), {"NOBITEX_AUTH_TOKEN": str(token)})
    return {
        "ok": True,
        "status": result.get("status"),
        "expiresIn": result.get("expiresIn"),
        "token_saved_to_env": write_env,
    }


def api_keys_list() -> list[dict[str, Any]]:
    load_env_file()
    token = token_from_env()
    return list_api_keys(token)


def api_keys_create(
    *,
    name: str,
    totp: str,
    permissions: str = "READ",
    description: str = "Created via Traderbot Lab",
    write_env: bool = False,
    env_file: Path | None = None,
) -> dict[str, Any]:
    load_env_file()
    token = token_from_env()
    result = create_api_key(
        token,
        name=name,
        permissions=permissions,
        totp=normalize_totp(totp),
        description=description,
    )
    if write_env and result.get("status") == "ok":
        public = (result.get("key") or {}).get("key") or ""
        private = result.get("privateKey") or ""
        if public and private:
            upsert_env_vars(
                env_file or Path(".env"),
                {
                    "NOBITEX_API_PUBLIC_KEY": public,
                    "NOBITEX_API_PRIVATE_KEY": private,
                },
            )
    return redact_apikey_response(dict(result))
