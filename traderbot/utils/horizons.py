from __future__ import annotations

from traderbot.utils.ml import horizon_label
from traderbot.utils.resolution import resolution_minutes

# Default export / eval windows for crypto (minutes, short name).
DEFAULT_FORECAST_HORIZONS: tuple[tuple[int, str], ...] = (
    (1, "1m"),
    (5, "5m"),
    (60, "1h"),
    (120, "2h"),
    (240, "4h"),
    (360, "6h"),
    (720, "12h"),
    (1440, "1d"),
)

FORECAST_TARGET_MINUTES: tuple[int, ...] = tuple(m for m, _ in DEFAULT_FORECAST_HORIZONS)
DEFAULT_EVAL_TARGET_MINUTES = 60


def forecast_horizons_for_resolution(resolution: str) -> list[tuple[int, str]]:
    """``(horizon_bars, label)`` for each default window that aligns with bar size."""
    bar_minutes = resolution_minutes(resolution)
    out: list[tuple[int, str]] = []
    seen_bars: set[int] = set()
    for target in FORECAST_TARGET_MINUTES:
        if target % bar_minutes != 0:
            continue
        horizon_bars = target // bar_minutes
        if horizon_bars < 1 or horizon_bars in seen_bars:
            continue
        seen_bars.add(horizon_bars)
        out.append((horizon_bars, horizon_label(bar_minutes, horizon_bars)))
    if not out:
        out.append((1, horizon_label(bar_minutes, 1)))
    return out


def default_eval_horizon(resolution: str) -> tuple[int, int]:
    """Return ``(horizon_bars, bar_minutes)`` using :data:`DEFAULT_EVAL_TARGET_MINUTES` when possible."""
    bar_minutes = resolution_minutes(resolution)
    horizons = forecast_horizons_for_resolution(resolution)
    for horizon_bars, _ in horizons:
        if horizon_bars * bar_minutes == DEFAULT_EVAL_TARGET_MINUTES:
            return horizon_bars, bar_minutes
    for prefer in (DEFAULT_EVAL_TARGET_MINUTES, 1440, 240, 60):
        for horizon_bars, _ in horizons:
            if horizon_bars * bar_minutes == prefer:
                return horizon_bars, bar_minutes
    return horizons[0][0], bar_minutes


def min_bars_for_forecast_eval(
    horizon_bars: int,
    *,
    train_ratio: float = 0.8,
    train_supervised_row_count: int | None = None,
) -> int:
    """Minimum OHLC rows for indicators, forward target, embargo, and holdout."""
    indicator_warmup = max(55, 35 + horizon_bars)
    if train_supervised_row_count is not None:
        min_supervised = max(20, train_supervised_row_count + horizon_bars + 10)
    else:
        min_supervised = max(20, int(horizon_bars / train_ratio) + horizon_bars + 10)
    return indicator_warmup + 30 + horizon_bars + min_supervised
