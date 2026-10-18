from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlencode

import requests

from traderbot.integrations.coinbeacon.cache import TtlCache, cache_ttl_for_path
from traderbot.integrations.coinbeacon.keys import coinbeacon_api_key_configured, load_coinbeacon_api_keys
from traderbot.integrations.coinbeacon.paths import COINBEACON_BASE_URL

__all__ = [
    "CoinBeaconClient",
    "CoinBeaconCredits",
    "CoinBeaconError",
    "coinbeacon_api_key_configured",
    "credits_from_headers",
]


class CoinBeaconError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        path: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.path = path


@dataclass(frozen=True, slots=True)
class CoinBeaconCredits:
    cost: int | None = None
    limit: int | None = None
    remaining: int | None = None
    reset: str | None = None
    limit_minute: int | None = None
    remaining_minute: int | None = None


def _parse_int_header(headers: Mapping[str, str], name: str) -> int | None:
    raw = headers.get(name)
    if raw is None or not str(raw).strip():
        return None
    try:
        return int(str(raw).strip())
    except ValueError:
        return None


def credits_from_headers(headers: Mapping[str, str]) -> CoinBeaconCredits:
    return CoinBeaconCredits(
        cost=_parse_int_header(headers, "X-Credits-Cost"),
        limit=_parse_int_header(headers, "X-Credits-Limit"),
        remaining=_parse_int_header(headers, "X-Credits-Remaining"),
        reset=headers.get("X-Credits-Reset"),
        limit_minute=_parse_int_header(headers, "X-RateLimit-Limit-Minute"),
        remaining_minute=_parse_int_header(headers, "X-RateLimit-Remaining-Minute"),
    )


class CoinBeaconClient:
    def __init__(
        self,
        *,
        api_keys: list[str] | None = None,
        api_key: str | None = None,
        base_url: str = COINBEACON_BASE_URL,
        session: requests.Session | None = None,
        cache: TtlCache | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        min_credits_remaining: int = 0,
    ) -> None:
        if api_keys is not None:
            resolved_keys = [item.strip() for item in api_keys if item.strip()]
        elif api_key:
            resolved_keys = [api_key.strip()]
        else:
            resolved_keys = load_coinbeacon_api_keys()
        if not resolved_keys:
            raise CoinBeaconError(
                "No CoinBeacon API keys configured. Set COINBEACON_API_KEY "
                "(and optional COINBEACON_API_KEY_ALT or COINBEACON_API_KEYS) on the Lab API host.",
            )
        self._api_keys = resolved_keys
        self._key_index = 0
        self._base_url = base_url.rstrip("/")
        self._session = session or requests.Session()
        self._cache = cache if cache is not None else TtlCache()
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._min_credits_remaining = max(0, min_credits_remaining)
        self.last_credits: CoinBeaconCredits | None = None

    @property
    def api_key_count(self) -> int:
        return len(self._api_keys)

    @property
    def active_key_index(self) -> int:
        return self._key_index

    def _active_api_key(self) -> str:
        return self._api_keys[self._key_index]

    def _rotate_api_key(self) -> bool:
        if self._key_index + 1 >= len(self._api_keys):
            return False
        self._key_index += 1
        return True

    def _credits_too_low(self) -> bool:
        if self._min_credits_remaining <= 0 or self.last_credits is None:
            return False
        remaining = self.last_credits.remaining
        return remaining is not None and remaining < self._min_credits_remaining

    def rotate_if_credits_low(self, min_remaining: int) -> bool:
        """Switch to the next configured key when daily credits are below min_remaining."""
        if min_remaining <= 0:
            return False
        if self.last_credits is None or self.last_credits.remaining is None:
            return False
        if self.last_credits.remaining >= min_remaining:
            return False
        return self._rotate_api_key()

    def get_public(
        self,
        path: str,
        *,
        params: dict[str, str | int | float | None] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        normalized_path = path.lstrip("/")
        if not normalized_path.startswith("public/"):
            normalized_path = f"public/{normalized_path}"
        query: dict[str, str] = {}
        if params:
            for key, value in params.items():
                if value is None:
                    continue
                query[str(key)] = str(value)
        cache_key = f"{normalized_path}?{urlencode(sorted(query.items()))}"
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        if self._credits_too_low() and self._rotate_api_key():
            pass

        url = f"{self._base_url}/{normalized_path}"
        if query:
            url = f"{url}?{urlencode(query)}"

        attempt = 0
        key_rotations = 0
        max_key_rotations = len(self._api_keys)

        while True:
            attempt += 1
            response = self._session.get(
                url,
                headers={"X-API-Key": self._active_api_key()},
                timeout=self._timeout_seconds,
            )
            self.last_credits = credits_from_headers(response.headers)

            if response.status_code == 429 and key_rotations < max_key_rotations - 1:
                if self._rotate_api_key():
                    key_rotations += 1
                    attempt = 0
                    continue

            if response.status_code == 429 and attempt <= self._max_retries:
                retry_after = response.headers.get("Retry-After")
                delay = 2.0
                if retry_after:
                    try:
                        delay = max(1.0, float(retry_after))
                    except ValueError:
                        pass
                time.sleep(delay)
                continue

            if response.status_code >= 400:
                detail = response.text[:500]
                raise CoinBeaconError(
                    f"CoinBeacon {response.status_code} on /{normalized_path}: {detail}",
                    status_code=response.status_code,
                    path=normalized_path,
                )

            payload = response.json()
            if not isinstance(payload, dict):
                raise CoinBeaconError(
                    f"CoinBeacon returned non-object JSON for /{normalized_path}",
                    path=normalized_path,
                )
            if use_cache:
                self._cache.set(cache_key, payload, cache_ttl_for_path(normalized_path))
            return payload

    def usage(self) -> dict[str, Any]:
        return self.get_public("public/usage", use_cache=True)
