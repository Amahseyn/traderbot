import numpy as np

from traderbot.algorithms.pair_trading.spread import spread_z_score_from_closes
from traderbot.algorithms.strategies.pair_trading import PairTradingAlgorithm
from traderbot.backtesting.pair_engine import run_pair_backtest


def _bars(closes: list[float], symbol: str = "BTCIRT") -> list[dict]:
    return [
        {
            "symbol": symbol,
            "resolution": "60",
            "timestamp": index * 3600,
            "open": price,
            "high": price * 1.001,
            "low": price * 0.999,
            "close": price,
            "volume": 1.0,
        }
        for index, price in enumerate(closes)
    ]


def test_spread_z_score_stable_series_near_zero():
    dominant = np.linspace(100.0, 110.0, 80)
    hedge = dominant * 0.5 + 2.0
    snapshot = spread_z_score_from_closes(dominant, hedge, lookback_period=30)
    assert snapshot is not None
    assert abs(snapshot.z_score) < 3.0


def test_spread_z_score_detects_divergence():
    dominant = np.linspace(100.0, 110.0, 80)
    hedge = dominant * 0.5 + 2.0
    hedge_with_spike = hedge.copy()
    hedge_with_spike[-5:] *= 1.08
    snapshot = spread_z_score_from_closes(dominant, hedge_with_spike, lookback_period=30)
    assert snapshot is not None
    assert snapshot.z_score > 1.0


def test_pair_backtest_runs_on_synthetic_correlated_series():
    bar_count = 120
    dominant_closes = [100.0 + index * 0.05 + (index % 7) * 0.2 for index in range(bar_count)]
    hedge_closes = [50.0 + index * 0.025 + (index % 7) * 0.1 for index in range(bar_count)]
    dominant_bars = _bars(dominant_closes, "BTCIRT")
    hedge_bars = _bars(hedge_closes, "ETHIRT")
    algorithm = PairTradingAlgorithm(lookback_period=30, entry_threshold=1.5, exit_threshold=0.4)
    result = run_pair_backtest(
        algorithm,
        dominant_bars,
        hedge_bars,
        initial_cash=10_000.0,
        fee_rate=0.001,
        slippage_rate=0.0005,
    )
    assert result.final_equity > 0
    assert len(result.equity_curve) == bar_count
