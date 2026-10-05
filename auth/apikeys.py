from __future__ import annotations

from typing import Any

from auth.session import request_with_token


def redact_apikey_response(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    if "privateKey" in out:
        out["privateKey"] = "<redacted; use write_env to persist>"
    return out


def list_api_keys(token: str) -> Any:
    return request_with_token("GET", "/apikeys/list", token=token)


def create_api_key(
    token: str,
    *,
    name: str,
    permissions: str,
    totp: str,
    description = "",
    ip_whitelist: list[str] | None = None,
    expiration_date: str | None = None,
) -> Any:
    body: dict[str, Any] = {
        "name": name,
        "description": description,
        "permissions": permissions,
        "ipAddressesWhitelist": ip_whitelist or [],
    }
    if expiration_date:
        body["expirationDate"] = expiration_date
    return request_with_token(
        "POST",
        "/apikeys/create",
        token=token,
        json_body=body,
        totp=totp,
    )
