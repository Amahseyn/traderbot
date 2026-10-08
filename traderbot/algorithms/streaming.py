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


class _RsiState(TypedDict):
    period: int
    prev_close: float | None
    avg_gain: float | None
    avg_loss: float | None
    seed_gains: list[float]
    seed_losses: list[float]


class _MacdState(TypedDict):
    fast_span: int
    slow_span: int
    signal_span: int
    fast: _EmaState
    slow: _EmaState
    signal: _EmaState
    bars_seen: int


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


def rsi_init(period: int) -> _RsiState:
    if period < 1:
        raise ValueError("period must be >= 1")
    return {
        "period": period,
        "prev_close": None,
        "avg_gain": None,
        "avg_loss": None,
        "seed_gains": [],
        "seed_losses": [],
    }


def rsi_reset(state: _RsiState) -> None:
    state["prev_close"] = None
    state["avg_gain"] = None
    state["avg_loss"] = None
    state["seed_gains"].clear()
    state["seed_losses"].clear()


def rsi_update(state: _RsiState, close: float) -> float | None:
    prev_close = state["prev_close"]
    state["prev_close"] = close
    if prev_close is None:
        return None
    delta = close - prev_close
    gain = delta if delta > 0 else 0.0
    loss = -delta if delta < 0 else 0.0
    period = state["period"]
    if state["avg_gain"] is None:
        state["seed_gains"].append(gain)
        state["seed_losses"].append(loss)
        if len(state["seed_gains"]) < period:
            return None
        state["avg_gain"] = sum(state["seed_gains"]) / period
        state["avg_loss"] = sum(state["seed_losses"]) / period
        state["seed_gains"].clear()
        state["seed_losses"].clear()
    else:
        state["avg_gain"] = (state["avg_gain"] * (period - 1) + gain) / period
        state["avg_loss"] = (state["avg_loss"] * (period - 1) + loss) / period
    avg_gain = state["avg_gain"]
    avg_loss = state["avg_loss"]
    if avg_loss == 0:
        return 50.0 if avg_gain == 0 else 100.0
    return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))


def macd_init(fast: int, slow: int, signal: int) -> _MacdState:
    if fast < 1 or slow < 1 or signal < 1:
        raise ValueError("macd periods must be >= 1")
    return {
        "fast_span": fast,
        "slow_span": slow,
        "signal_span": signal,
        "fast": ema_init(fast),
        "slow": ema_init(slow),
        "signal": ema_init(signal),
        "bars_seen": 0,
    }


def macd_reset(state: _MacdState) -> None:
    ema_reset(state["fast"])
    ema_reset(state["slow"])
    ema_reset(state["signal"])
    state["bars_seen"] = 0


def macd_update(
    state: _MacdState,
    close: float,
) -> tuple[float | None, float | None, float | None]:
    state["bars_seen"] += 1
    fast_v = ema_update(state["fast"], close)
    slow_v = ema_update(state["slow"], close)
    bar_index = state["bars_seen"] - 1
    if bar_index < state["slow_span"] - 1:
        return None, None, None
    line = fast_v - slow_v
    signal_v = ema_update(state["signal"], line)
    histogram = line - signal_v
    return line, signal_v, histogram
