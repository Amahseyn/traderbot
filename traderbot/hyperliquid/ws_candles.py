"""Hyperliquid websocket candle feed (public, no keys) with a health check for REST fallback.

The ``candle`` subscription pushes the forming candle on every trade. A candle is treated as
closed when a newer open time arrives, or when its close time has passed (quiet markets).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


class HyperliquidCandleStream:
    def __init__(
        self,
        *,
        coin: str,
        interval: str,
        bar_seconds: int,
        normalize: Callable[[dict[str, Any]], dict[str, Any]],
        info_factory: Callable[[], Any] | None = None,
        stale_after_seconds: float | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.coin = coin
        self.interval = interval
        self.bar_seconds = int(bar_seconds)
        self._normalize = normalize
        self._info_factory = info_factory
        self._stale_after = float(stale_after_seconds or max(30.0, 2.0 * bar_seconds))
        self._clock = clock
        self._lock = threading.Lock()
        self._forming: dict[str, Any] | None = None
        self._closed: list[dict[str, Any]] = []
        self._last_message_at: float | None = None
        self._info: Any = None
        self._failed = False

    def start(self) -> bool:
        try:
            if self._info_factory is not None:
                self._info = self._info_factory()
            else:
                from hyperliquid.info import Info
                from hyperliquid.utils import constants

                self._info = Info(constants.MAINNET_API_URL, skip_ws=False)
            self._info.subscribe({"type": "candle", "coin": self.coin, "interval": self.interval}, self.on_message)
        except Exception as exc:  # network / SDK errors: fall back to REST
            logger.warning("Hyperliquid candle websocket unavailable, using REST polling: %s", exc)
            self._failed = True
            return False
        self._last_message_at = self._clock()
        return True

    def stop(self) -> None:
        info = self._info
        self._info = None
        try:
            if info is not None and getattr(info, "ws_manager", None) is not None:
                info.ws_manager.stop()
        except Exception:  # pragma: no cover - best effort
            pass

    def on_message(self, message: dict[str, Any]) -> None:
        data = message.get("data") if isinstance(message, dict) else None
        if not isinstance(data, dict) or "t" not in data:
            return
        with self._lock:
            self._last_message_at = self._clock()
            forming = self._forming
            if forming is not None and int(data["t"]) > int(forming["t"]):
                self._closed.append(self._normalize(forming))
            if forming is None or int(data["t"]) >= int(forming["t"]):
                self._forming = dict(data)

    def healthy(self) -> bool:
        if self._failed or self._info is None or self._last_message_at is None:
            return False
        return self._clock() - self._last_message_at <= self._stale_after

    def drain_closed(self) -> list[dict[str, Any]]:
        with self._lock:
            now = self._clock()
            forming = self._forming
            if forming is not None and int(forming["t"]) / 1000 + self.bar_seconds <= now:
                self._closed.append(self._normalize(forming))
                self._forming = None
            closed, self._closed = self._closed, []
        return closed
