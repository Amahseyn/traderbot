from __future__ import annotations

import json
from typing import Any

import requests

from traderbot.client import BASE_URL, USER_AGENT, NobitexClientError
from traderbot.auth.session import normalize_totp


def login_v2(
    *,
    username: str,
    password: str,
    totp: str | None = None,
    remember: bool = False,
    base_url: str = BASE_URL,
) -> dict[str, Any]:
    """
    Bot login: POST /v2/auth/login with captcha=api and optional X-TOTP.
    Returns parsed JSON (success includes ``key`` session token).
    """
    payload: dict[str, Any] = {
        "username": username.strip(),
        "password": password,
        "captcha": "api",
    }
    if remember:
        payload["remember"] = "yes"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    if totp:
        headers["X-TOTP"] = normalize_totp(totp)

    url = f"{base_url.rstrip('/')}/v2/auth/login"
    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=60,
    )
    try:
        parsed = response.json()
    except json.JSONDecodeError:
        parsed = response.text
    if response.status_code != 200:
        raise NobitexClientError("login failed", response.status_code, parsed)
    return parsed
