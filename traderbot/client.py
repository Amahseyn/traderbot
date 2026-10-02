from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

import requests

from traderbot.signing import sign_request

BASE_URL = "https://apiv2.nobitex.ir"
USER_AGENT = "TraderBot/traderbot-0.1.0"


class NobitexClientError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class NobitexClient:
    def __init__(
        self,
        public_key: str,
        private_key: str,
        *,
        base_url: str = BASE_URL,
        request_fn: Callable[..., requests.Response] | None = None,
    ):
        self._public_key = public_key.strip()
        self._private_key = private_key.strip()
        self._base_url = base_url.rstrip("/")
        self._request_fn = request_fn

    @classmethod
    def from_env(cls, request_fn: Callable[..., requests.Response] | None = None) -> NobitexClient:
        public_key = os.environ.get("NOBITEX_API_PUBLIC_KEY", "").strip()
        private_key = os.environ.get("NOBITEX_API_PRIVATE_KEY", "").strip()
        if not public_key or not private_key:
            raise NobitexClientError("Set NOBITEX_API_PUBLIC_KEY and NOBITEX_API_PRIVATE_KEY")
        return cls(
            public_key,
            private_key,
            base_url=os.environ.get("NOBITEX_API_BASE", BASE_URL),
            request_fn=request_fn,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        if not path.startswith("/"):
            path = f"/{path}"
        if params:
            path += "?" + urlencode({k: v for k, v in params.items() if v is not None})

        body = ""
        data = None
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if json_body is not None:
            body = json.dumps(json_body, separators=(",", ":"), ensure_ascii=False)
            headers["Content-Type"] = "application/json"
            data = body

        signature, timestamp = sign_request(
            private_key_b64=self._private_key,
            method=method,
            full_path=path,
            body=body,
        )
        headers["Nobitex-Key"] = self._public_key
        headers["Nobitex-Signature"] = signature
        headers["Nobitex-Timestamp"] = timestamp

        url = f"{self._base_url}{path}"
        if self._request_fn:
            response = self._request_fn(method.upper(), url, headers=headers, data=data, timeout=60)
        else:
            response = requests.request(method.upper(), url, headers=headers, data=data, timeout=60)

        try:
            parsed = response.json()
        except json.JSONDecodeError:
            parsed = response.text
        if response.status_code != 200:
            raise NobitexClientError(f"{method} {path} failed", response.status_code, parsed)
        return parsed
