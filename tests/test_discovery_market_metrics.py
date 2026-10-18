from __future__ import annotations

from typing import Any

import pytest

from traderbot.discovery.market_metrics import (
    compute_market_bar_metrics,
    score_market_opportunity,
    volume_percentiles,
)


def _bars_with_trend(count: int, start: float = 100.0, step: float = 0.5) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    price = start
    for index in range(count):
        rows.append(
            {
                "timestamp": 1_700_000_000 + index * 86_400,
                "open": price,
                "high": price * 1.01,
                "low": price * 0.99,
                "close": price,
                "volume": 1000.0 + index,
            },
        )
        price += step
    return rows


def test_compute_market_bar_metrics_positive_trend() -> None:
    bars = _bars_with_trend(40)
    metrics = compute_market_bar_metrics(bars)
    assert metrics.mean_quote_volume > 0
    assert metrics.return_1bar_pct is not None
    assert metrics.return_7bar_pct is not None
    assert metrics.return_1bar_pct > 0
    assert metrics.realized_vol_pct is not None


def test_score_market_opportunity_uses_volume_percentile() -> None:
    bars = _bars_with_trend(40)
    metrics = compute_market_bar_metrics(bars)
    low, _ = score_market_opportunity(metrics, volume_percentile=0.2)
    high, _ = score_market_opportunity(metrics, volume_percentile=0.9)
    assert low is not None and high is not None
    assert high > low


def test_volume_percentiles_spread() -> None:
    percentiles = volume_percentiles([10.0, 20.0, 100.0])
    assert percentiles == [0.0, 0.5, 1.0]
