import math

from traderbot.ml.simulator import final_equity_from_curve, simulate_holdout_account


def _series(closes: list[float], *, bar_sec: int = 3600) -> list[tuple[int, float]]:
    t0 = 1_700_000_000
    return [(t0 + i * bar_sec, c) for i, c in enumerate(closes)]


def test_non_overlapping_trades_do_not_multiply_every_bar():
    """Four consecutive overlapping labels; only two non-overlapping long trades."""
    bar_sec = 3600
    horizon = 4
    ts = [0, bar_sec, 2 * bar_sec, 3 * bar_sec]
    y_true = [0.10, 0.10, 0.10, 0.10]
    y_pred = [1.0, 1.0, 1.0, 1.0]
    prices = _series([100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0], bar_sec=bar_sec)
    # shift timestamps to match price series
    t0 = prices[0][0]
    ts = [t0 + i * bar_sec for i in range(8)]
    y_true = [0.10] * 8
    y_pred = [1.0] * 8

    out = simulate_holdout_account(
        y_true,
        y_pred,
        ts,
        horizon_bars=horizon,
        bar_minutes=60,
        price_series=prices,
        initial_usd=100.0,
    )
    # Long at t0 and again at t0+4h (non-overlapping 4h holds)
    expected = 100.0 * math.exp(0.20)
    assert abs(out.metrics["strategy_final_usd"] - expected) < 0.01
    assert out.metrics["strategy_trades"] == 2.0
    assert abs(final_equity_from_curve(out.strategy_equity) - expected) < 0.01


def test_buy_hold_uses_close_ratio():
    bar_sec = 3600
    horizon = 2
    prices = _series([100.0, 110.0, 121.0, 133.1], bar_sec=bar_sec)
    t0 = prices[0][0]
    ts = [t0, t0 + bar_sec]
    y_true = [math.log(1.1), math.log(1.1)]
    y_pred = [-1.0, -1.0]

    out = simulate_holdout_account(
        y_true,
        y_pred,
        ts,
        horizon_bars=horizon,
        bar_minutes=60,
        price_series=prices,
        initial_usd=100.0,
    )
    # Hold from t0 through last window end (t0 + bar + 2*bar_sec) -> close at index 3
    assert abs(out.metrics["buy_hold_final_usd"] - 133.1) < 0.01
    assert out.metrics["strategy_trades"] == 0.0
    assert out.metrics["strategy_final_usd"] == 100.0


def test_curve_final_matches_metrics():
    bar_sec = 60
    prices = _series([50.0, 52.0, 54.0, 56.0, 58.0, 60.0], bar_sec=bar_sec)
    t0 = prices[0][0]
    ts = [t0, t0 + bar_sec, t0 + 2 * bar_sec]
    y_true = [0.02, -0.01, 0.03]
    y_pred = [0.5, 0.5, -0.5]

    out = simulate_holdout_account(
        y_true,
        y_pred,
        ts,
        horizon_bars=2,
        bar_minutes=1,
        price_series=prices,
        initial_usd=100.0,
    )
    assert abs(final_equity_from_curve(out.strategy_equity) - out.metrics["strategy_final_usd"]) < 1e-9
    assert len(out.strategy_equity) == len(out.buy_hold_equity)
