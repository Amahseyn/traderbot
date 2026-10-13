from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from auth.apikeys import create_api_key, list_api_keys, redact_apikey_response
from auth.envfile import load_env_file, upsert_env_vars
from auth.login import login_v2
from auth.session import normalize_totp, token_from_env
from traderbot.hyperliquid.credentials import (
    PRIVATE_KEY_ENV,
    WALLET_ADDRESS_ENV,
    hyperliquid_trading_configured,
    hyperliquid_wallet_configured,
    normalize_wallet_address,
)
from traderbot.hyperliquid.info_client import hyperliquid_info
from traderbot.nobitex.client import NobitexClient
from traderbot.nobitex.profile import nobitex_keys_configured


def auth_status() -> dict[str, Any]:
    from lab.config import lab_api_auth_enabled

    load_env_file()
    token = os.environ.get("NOBITEX_AUTH_TOKEN", "").strip()
    return {
        "api_keys_configured": nobitex_keys_configured(),
        "auth_token_configured": bool(token),
        "hyperliquid_wallet_configured": hyperliquid_wallet_configured(),
        "hyperliquid_trading_configured": hyperliquid_trading_configured(),
        "live_exchange_default": "hyperliquid",
        "lab_api_auth_enabled": lab_api_auth_enabled(),
        "lab_api_token_configured": bool(os.environ.get("LAB_API_TOKEN", "").strip()),
    }


def fetch_hyperliquid_account() -> dict[str, Any]:
    load_env_file()
    address = normalize_wallet_address(os.environ.get(WALLET_ADDRESS_ENV, ""))
    state = hyperliquid_info().user_state(address)
    margin = state.get("marginSummary") or {}
    return {
        "wallet_address": address,
        "account_value_usd": float(margin.get("accountValue") or 0.0),
        "total_margin_used": float(margin.get("totalMarginUsed") or 0.0),
        "positions": state.get("assetPositions") or [],
    }


def save_hyperliquid_credentials(
    *,
    wallet_address: str,
    private_key: str | None = None,
    write_env: bool = False,
    env_file: Path | None = None,
) -> dict[str, Any]:
    load_env_file()
    address = normalize_wallet_address(wallet_address)
    updates: dict[str, str] = {WALLET_ADDRESS_ENV: address}
    saved_private_key = False
    if private_key is not None and str(private_key).strip():
        updates[PRIVATE_KEY_ENV] = str(private_key).strip()
        saved_private_key = True
    if write_env:
        upsert_env_vars(env_file or Path(".env"), updates)
        load_env_file()
    return {
        "ok": True,
        "wallet_address": address,
        "private_key_saved": saved_private_key,
        "saved_to_env": write_env,
        "trading_configured": hyperliquid_trading_configured(),
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
