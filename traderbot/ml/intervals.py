from __future__ import annotations

# Default forecast windows for crypto (minutes, short name).
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

# Preferred default when running a single eval (CLI / batch) for a given candle resolution.
DEFAULT_EVAL_TARGET_MINUTES = 60


def resolution_minutes(resolution: str) -> int:
    if resolution.isdigit():
        return int(resolution)
    if resolution == "D":
        return 24 * 60
    if resolution == "2D":
        return 2 * 24 * 60
    if resolution == "3D":
        return 3 * 24 * 60
    raise ValueError(f"unknown resolution: {resolution}")


def resolution_from_csv_path(csv_path: str) -> str:
    """``BTCIRT_60.csv`` -> ``60``."""
    return csv_path.rsplit("_", 1)[-1].removesuffix(".csv")


def forecast_horizons_for_resolution(resolution: str) -> list[tuple[int, str]]:
    """
    ``(horizon_bars, label)`` for each default forecast window that aligns with bar size.

    Windows: 1m, 5m, 1h, 2h, 4h, 6h, 12h, 1d. Duplicate bar counts are listed once.
    If none align (e.g. very coarse candles), use a single-bar horizon.
    """
    from traderbot.ml.utils import horizon_label

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
    train_ratio = 0.8,
    train_supervised_row_count: int | None = None,
) -> int:
    """
    Minimum OHLC rows for indicators, forward target, horizon embargo, and holdout.

    Ensures enough supervised rows that training can finish ``horizon_bars`` before
    the first test row (no label leakage).
    """
    indicator_warmup = max(55, 35 + horizon_bars)
    if train_supervised_row_count is not None:
        min_supervised = max(20, train_supervised_row_count + horizon_bars + 10)
    else:
        min_supervised = max(20, int(horizon_bars / train_ratio) + horizon_bars + 10)
    return indicator_warmup + 30 + horizon_bars + min_supervised
