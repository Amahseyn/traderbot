from __future__ import annotations

import math
from collections import deque
from typing import TypedDict


class _BollingerState(TypedDict):
    period: int
    num_std: float
    buf: deque[float]


def bollinger_init(*, period: int, num_std: float) -> _BollingerState:
    if period < 1:
        raise ValueError("period must be >= 1")
    if num_std <= 0:
        raise ValueError("num_std must be positive")
    return {"period": period, "num_std": num_std, "buf": deque(maxlen=period)}


def bollinger_reset(state: _BollingerState) -> None:
    state["buf"].clear()


def bollinger_update(state: _BollingerState, close: float) -> tuple[float, float, float] | None:
    """Return ``(lower, upper, mean)`` once ``period`` closes are buffered."""
    state["buf"].append(close)
    if len(state["buf"]) < state["period"]:
        return None
    return bollinger_levels(list(state["buf"]), period=state["period"], num_std=state["num_std"])


def bollinger_levels(
    closes: list[float],
    *,
    period: int,
    num_std: float,
) -> tuple[float, float, float] | None:
    """Return ``(lower, upper, mean)`` for the last ``period`` closes, or None if too short."""
    if len(closes) < period:
        return None
    window = closes[-period:]
    mean = sum(window) / period
    variance = sum((x - mean) ** 2 for x in window) / period
    std = math.sqrt(variance)
    return mean - num_std * std, mean + num_std * std, mean
