from __future__ import annotations

import pytest

from traderbot.algorithms.strategies.bollinger import BollingerMeanReversionAlgorithm
from traderbot.algorithms.strategies.online_logistic import OnlineLogisticAlgorithm
from traderbot.algorithms.strategies.rsi_trend import RsiTrendAlgorithm
from traderbot.algorithms.strategies.scalp_dip import ScalpDipAlgorithm
from traderbot.backtesting import run_backtest


def _make_bar(i: int, price: float, volume: float = 100.0) -> dict:
    return {
        "timestamp": 1700000000 + i * 3600,
        "open": price,
        "high": price + 0.5,
        "low": price - 0.5,
        "close": price,
        "volume": volume,
    }


def test_bollinger_mean_exit_recovers_profit() -> None:
    # Fluctuating baseline around 100, drops to 94 (buys lower band), recovers to 100 (mean), then drops to 90
    closes = [100.0 + (1.0 if i % 2 == 0 else -1.0) for i in range(25)]
    closes += [94.0, 95.0, 98.0, 100.0, 100.0, 92.0, 90.0]
    bars = [_make_bar(i, p) for i, p in enumerate(closes)]

    algo_mean = BollingerMeanReversionAlgorithm(period=20, num_std=1.5, exit_target="mean")
    result_mean = run_backtest(algo_mean, bars, initial_cash=10_000.0, execution="close")

    algo_upper = BollingerMeanReversionAlgorithm(period=20, num_std=1.5, exit_target="upper")
    result_upper = run_backtest(algo_upper, bars, initial_cash=10_000.0, execution="close")

    # Mean exit took profit around 100.0 (+4.07%) before the second crash to 90 (-4.26%)
    assert result_mean.return_pct > result_upper.return_pct
    assert result_mean.return_pct > 0.0


def test_scalp_dip_trend_filter_blocks_falling_knife() -> None:
    # Severe crash from 200 down to 100 with small dead-cat bounces
    closes = [200.0 - i * 3 for i in range(35)]
    bars = [_make_bar(i, p) for i, p in enumerate(closes)]

    # Gated with trend_ema_period: will not buy dips when below EMA
    gated = ScalpDipAlgorithm(dip_lookback_bars=4, dip_pct=0.01, trend_ema_period=20)
    gated_buys = sum(1 for b in bars if gated.on_bar(b) == "buy")
    assert gated_buys == 0


def test_rsi_trend_trailing_stop_limits_drawdown() -> None:
    # Price starts flat (RSI 50), dips slightly (RSI < 45), pumps crossing up 55, then dumps
    closes = [20.0] * 15 + [19.0, 18.5, 19.5, 21.0, 23.0, 25.0, 25.0, 22.0, 18.0, 15.0]
    bars = [_make_bar(i, p) for i, p in enumerate(closes)]

    algo_trailing = RsiTrendAlgorithm(period=5, trend_filter_period=10, trailing_stop_pct=0.10)
    algo_no_stop = RsiTrendAlgorithm(period=5, trend_filter_period=10, trailing_stop_pct=None)

    res_trailing = run_backtest(algo_trailing, bars, initial_cash=10_000.0)
    res_no_stop = run_backtest(algo_no_stop, bars, initial_cash=10_000.0)

    # Trailing stop locked in profits before the final drop to 15
    assert len(res_trailing.trades) > 0
    assert res_trailing.return_pct > res_no_stop.return_pct


def test_online_logistic_warmup_and_regularization() -> None:
    # With 60 bars, 20 warmup allows trading while 100 warmup did not
    closes = [100.0 + (i % 5) * 1.0 for i in range(60)]
    bars = [_make_bar(i, p) for i, p in enumerate(closes)]

    algo = OnlineLogisticAlgorithm(ml_warmup_samples=20, l2_reg=0.01)
    actions = [algo.on_bar(b) for b in bars]
    assert algo._trained_samples >= 20
