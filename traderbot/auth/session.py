from __future__ import annotations

import json
import os
from typing import Any

import requests

from traderbot.client import BASE_URL, USER_AGENT, NobitexClientError

DEFAULT_TIMEOUT = 60


def normalize_totp(value: str) -> str:
    return value.replace(" ", "").strip()


def token_from_env() -> str:
    token = os.environ.get("NOBITEX_AUTH_TOKEN", "").strip()
    if not token:
        raise NobitexClientError(
            "Set NOBITEX_AUTH_TOKEN (traderbot auth login) or pass --token"
        )
    return token


def request_with_token(
    method: str,
    path: str,
    *,
    token: str,
    json_body: dict[str, Any] | None = None,
    totp: str | None = None,
    base_url: str | None = None,
) -> Any:
    if not path.startswith("/"):
        path = f"/{path}"
    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
        "Authorization": f"Token {token}",
    }
    if totp:
        headers["X-TOTP"] = normalize_totp(totp)
    body = None
    data = None
    if json_body is not None:
        body = json.dumps(json_body, separators=(",", ":"), ensure_ascii=False)
        headers["Content-Type"] = "application/json"
        data = body

    url = f"{(base_url or os.environ.get('NOBITEX_API_BASE', BASE_URL)).rstrip('/')}{path}"
    response = requests.request(method.upper(), url, headers=headers, data=data, timeout=DEFAULT_TIMEOUT)
    try:
        parsed = response.json()
    except json.JSONDecodeError:
        parsed = response.text
    if response.status_code != 200:
        raise NobitexClientError(f"{method} {path} failed", response.status_code, parsed)
    return parsed
