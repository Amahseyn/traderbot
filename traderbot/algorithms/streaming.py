from __future__ import annotations

from collections import deque
from typing import TypedDict


class _RollingMeanState(TypedDict):
    window: int
    buf: deque[float]
    sum: float


class _EmaState(TypedDict):
    alpha: float
    value: float | None


class _AtrState(TypedDict):
    period: int
    true_ranges: list[float]
    atr_value: float | None
    prev_close: float | None


def rolling_mean_init(window: int) -> _RollingMeanState:
    if window < 1:
        raise ValueError("window must be >= 1")
    return {"window": window, "buf": deque(maxlen=window), "sum": 0.0}


def rolling_mean_reset(state: _RollingMeanState) -> None:
    state["buf"].clear()
    state["sum"] = 0.0


def rolling_mean_update(state: _RollingMeanState, value: float) -> float | None:
    buf = state["buf"]
    if len(buf) == state["window"]:
        state["sum"] -= buf[0]
    buf.append(value)
    state["sum"] += value
    if len(buf) < state["window"]:
        return None
    return state["sum"] / state["window"]


def ema_init(span: int) -> _EmaState:
    if span < 1:
        raise ValueError("span must be >= 1")
    return {"alpha": 2.0 / (span + 1), "value": None}


def ema_reset(state: _EmaState) -> None:
    state["value"] = None


def ema_update(state: _EmaState, value: float) -> float:
    prev = state["value"]
    if prev is None:
        state["value"] = value
    else:
        state["value"] = state["alpha"] * value + (1.0 - state["alpha"]) * prev
    return state["value"]


def atr_init(period: int) -> _AtrState:
    if period < 1:
        raise ValueError("period must be >= 1")
    return {"period": period, "true_ranges": [], "atr_value": None, "prev_close": None}


def atr_reset(state: _AtrState) -> None:
    state["true_ranges"].clear()
    state["atr_value"] = None
    state["prev_close"] = None


def atr_update(state: _AtrState, *, high: float, low: float, close: float) -> float | None:
    prev_close = state["prev_close"]
    if prev_close is None:
        true_range = high - low
    else:
        true_range = max(high - low, abs(high - prev_close), abs(low - prev_close))
    state["prev_close"] = close
    state["true_ranges"].append(true_range)
    period = state["period"]
    if len(state["true_ranges"]) < period:
        return None
    if state["atr_value"] is None:
        state["atr_value"] = sum(state["true_ranges"][:period]) / period
    else:
        state["atr_value"] = (state["atr_value"] * (period - 1) + true_range) / period
    return state["atr_value"]
