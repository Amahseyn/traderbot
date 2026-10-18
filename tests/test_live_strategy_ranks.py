from __future__ import annotations

from lab.live_strategy_ranks import rank_strategies_on_live_bars


def _synthetic_bars(count: int = 80) -> list[dict]:
    return [
        {
            "symbol": "BTCUSDT",
            "resolution": "60",
            "timestamp": 1_700_000_000 + index * 3600,
            "open": 100.0 + index * 0.1,
            "high": 101.0 + index * 0.1,
            "low": 99.0 + index * 0.1,
            "close": 100.0 + index * 0.1,
            "volume": 1.0,
        }
        for index in range(count)
    ]


def test_rank_strategies_on_live_bars_sorted(monkeypatch):
    monkeypatch.setattr(
        "lab.live_strategy_ranks.fetch_live_tune_bars",
        lambda **_kwargs: _synthetic_bars(),
    )
    payload = rank_strategies_on_live_bars(
        exchange="hyperliquid",
        src="btc",
        dst="usdt",
        resolution="60",
        max_bars=80,
    )
    ranked = payload["ranked"]
    assert len(ranked) >= 2
    returns = [row["return_pct"] for row in ranked if row.get("return_pct") is not None]
    assert returns == sorted(returns, reverse=True)
    assert ranked[0]["rank"] == 1
