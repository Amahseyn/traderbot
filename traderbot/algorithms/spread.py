from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import log


@dataclass(slots=True)
class SpreadZScoreState:
    lookback: int
    log_spreads: deque[float]
    sum: float
    sum_sq: float


def spread_zscore_init(lookback: int) -> SpreadZScoreState:
    if lookback < 2:
        raise ValueError("lookback must be at least 2")
    return SpreadZScoreState(
        lookback=lookback,
        log_spreads=deque(),
        sum=0.0,
        sum_sq=0.0,
    )


def spread_zscore_reset(state: SpreadZScoreState) -> None:
    state.log_spreads.clear()
    state.sum = 0.0
    state.sum_sq = 0.0


def _subtract_spread(state: SpreadZScoreState, value: float) -> None:
    state.sum -= value
    state.sum_sq -= value * value


def spread_zscore_update(
    state: SpreadZScoreState,
    primary_close: float,
    hedge_close: float,
    hedge_ratio: float,
) -> float | None:
    if primary_close <= 0 or hedge_close <= 0:
        return None
    log_spread = log(primary_close) - hedge_ratio * log(hedge_close)
    if len(state.log_spreads) >= state.lookback:
        oldest = state.log_spreads.popleft()
        _subtract_spread(state, oldest)
    state.log_spreads.append(log_spread)
    state.sum += log_spread
    state.sum_sq += log_spread * log_spread
    count = len(state.log_spreads)
    if count < state.lookback:
        return None
    mean = state.sum / count
    variance = max(state.sum_sq / count - mean * mean, 0.0)
    if variance <= 0:
        return 0.0
    return (log_spread - mean) / variance**0.5


def rolling_hedge_ratio(
    primary_closes: deque[float],
    hedge_closes: deque[float],
) -> float | None:
    """OLS slope of log(primary) on log(hedge) over the window (causal at window end)."""
    count = len(primary_closes)
    if count < 2 or count != len(hedge_closes):
        return None
    log_x = [log(value) for value in hedge_closes]
    log_y = [log(value) for value in primary_closes]
    mean_x = sum(log_x) / count
    mean_y = sum(log_y) / count
    var_x = sum((value - mean_x) ** 2 for value in log_x)
    if var_x <= 0:
        return 1.0
    cov = sum((log_x[index] - mean_x) * (log_y[index] - mean_y) for index in range(count))
    return cov / var_x
