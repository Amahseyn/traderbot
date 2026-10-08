from __future__ import annotations

import time
from typing import Any

import requests
from requests.exceptions import ConnectionError, SSLError, Timeout

from traderbot.utils.constants import (
    NOBITEX_HTTP_RETRY_ATTEMPTS,
    NOBITEX_HTTP_RETRY_BASE_SECONDS,
)

_RETRYABLE = (SSLError, ConnectionError, Timeout)


def http_get_with_retries(
    url: str,
    *,
    headers: dict[str, str],
    timeout: float,
    params: dict[str, Any] | None = None,
    session: requests.Session | None = None,
    attempts: int = NOBITEX_HTTP_RETRY_ATTEMPTS,
) -> requests.Response:
    """GET with exponential backoff on transient TLS/network failures."""
    http = session or requests
    last_error: BaseException | None = None
    for attempt_index in range(max(1, attempts)):
        try:
            response = http.get(url, headers=headers, timeout=timeout, params=params)
            response.raise_for_status()
            return response
        except _RETRYABLE as exc:
            last_error = exc
            if attempt_index + 1 >= attempts:
                break
            time.sleep(NOBITEX_HTTP_RETRY_BASE_SECONDS * (2**attempt_index))
    if last_error is not None:
        raise last_error
    raise RuntimeError("http_get_with_retries failed without an exception")
