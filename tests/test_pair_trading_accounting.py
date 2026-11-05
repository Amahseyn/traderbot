import pytest
from traderbot.algorithms.strategies.pair_trading import PairTradingAlgorithm
from traderbot.backtesting.pair_engine import run_pair_backtest, run_perp_pair_backtest


def _make_bar(symbol: str, timestamp: int, price: float) -> dict:
    return {
        "symbol": symbol,
        "resolution": "60",
        "timestamp": timestamp,
        "open": price,
        "high": price * 1.001,
        "low": price * 0.999,
        "close": price,
        "volume": 100.0,
    }


def test_perp_pair_backtest_realizes_profit_on_close():
    """
    Audit regression: Verify that closing both legs realizes accumulated PnL into account equity
    rather than losing unrealized PnL when positions are zeroed.
    """
    # 40 warmup bars with equal prices (100)
    # Then dominant stays at 100, hedge spikes to 120 (triggering long_spread: buy dominant, short hedge)
    # Then spread mean reverts back (hedge drops to 100) triggering close_spread.
    # The short hedge position made profit: entered at ~120, closed at ~100.
    # The dominant position broke even: entered at 100, closed at 100.
    # Final equity MUST be strictly greater than initial cash (minus trading fees).
    dominant_bars = []
    hedge_bars = []

    for index in range(65):
        t = index * 3600
        p_d = 100.0
        # Warmup at 100
        if index < 25:
            p_h = 100.0
        elif index < 32:
            p_h = 130.0  # Spike -> triggers entry (short hedge, long dominant)
        else:
            p_h = 100.0  # Mean reversion -> triggers close_spread
        dominant_bars.append(_make_bar("BTCUSDT", t, p_d))
        hedge_bars.append(_make_bar("ETHUSDT", t, p_h))

    algo = PairTradingAlgorithm(lookback_period=20, entry_threshold=1.5, exit_threshold=0.8)
    result = run_perp_pair_backtest(
        algo,
        dominant_bars,
        hedge_bars,
        initial_cash=10_000.0,
        fee_rate=0.001,
        slippage_rate=0.0,
        position_fraction=0.5,
    )

    # Ensure a trade was opened and closed
    assert len(result.trades) >= 4, "Expected at least 2 entry trades and 2 exit trades"
    # The short hedge leg was opened around 130 and closed at 100 -> profitable round trip!
    # With correct futures accounting, final_equity should be significantly > 10,000.
    assert result.final_equity > 10_050.0, (
        f"Realized PnL was lost upon closing positions! final_equity={result.final_equity}"
    )


def test_perp_pair_backtest_realizes_loss_on_close():
    """
    Audit regression: Verify that a losing trade actually decreases cash/equity rather
    than reverting back to initial_cash upon position closure.
    """
    dominant_bars = []
    hedge_bars = []

    for index in range(50):
        t = index * 3600
        p_d = 100.0
        if index < 25:
            p_h = 100.0
        elif index < 35:
            p_h = 130.0  # triggers entry (short hedge, long dominant)
        else:
            p_h = 160.0  # spread expands further, exit on stop / close
        dominant_bars.append(_make_bar("BTCUSDT", t, p_d))
        hedge_bars.append(_make_bar("ETHUSDT", t, p_h))

    # Force close via exit threshold or test logic
    algo = PairTradingAlgorithm(lookback_period=20, entry_threshold=1.5, exit_threshold=0.5)
    # If the trade is closed at 160 when shorted at 130, it suffered a loss.
    # Even if it stayed open, if we close it, equity must reflect the loss.
    result = run_perp_pair_backtest(
        algo,
        dominant_bars,
        hedge_bars,
        initial_cash=10_000.0,
        fee_rate=0.001,
        slippage_rate=0.0,
        position_fraction=0.5,
    )
    # The position suffered an adverse move on hedge from 130 to 160
    assert result.final_equity < 9_800.0, (
        f"Losing trade did not reflect loss! final_equity={result.final_equity}"
    )


def test_perp_pair_backtest_asymmetric_hedge_ratio_entry_equity():
    """
    Audit regression: Verify that opening positions with hedge_ratio != 1.0 does not cause
    an immediate artificial jump in equity at the entry bar.
    """
    dominant_bars = []
    hedge_bars = []

    for index in range(40):
        t = index * 3600
        p_d = 100.0
        p_h = 100.0 if index < 25 else 125.0
        dominant_bars.append(_make_bar("BTCUSDT", t, p_d))
        hedge_bars.append(_make_bar("ETHUSDT", t, p_h))

    algo = PairTradingAlgorithm(lookback_period=20, entry_threshold=1.5, exit_threshold=0.5)
    initial_cash = 10_000.0
    result = run_perp_pair_backtest(
        algo,
        dominant_bars,
        hedge_bars,
        initial_cash=initial_cash,
        fee_rate=0.0,
        slippage_rate=0.0,
        hedge_ratio=2.0,  # asymmetric hedge ratio
        position_fraction=0.5,
    )
    # At the moment of trade entry, equity should not jump wildly from 10,000 when fee_rate=0
    for timestamp, equity in result.equity_curve:
        assert abs(equity - initial_cash) < 1000.0, (
            f"Artificial equity jump detected at t={timestamp}: equity={equity}"
        )


def test_spot_pair_backtest_unwinds_on_close_spread():
    """
    Audit regression: Verify that spot pair trading unwinds / rebalances back to target weights
    upon close_spread, rather than leaving the portfolio permanently distorted.
    """
    dominant_bars = []
    hedge_bars = []

    for index in range(65):
        t = index * 3600
        p_d = 100.0
        if index < 25:
            p_h = 100.0
        elif index < 32:
            p_h = 130.0  # Divergence -> long_spread
        else:
            p_h = 100.0  # Convergence -> close_spread
        dominant_bars.append(_make_bar("BTCIRT", t, p_d))
        hedge_bars.append(_make_bar("ETHIRT", t, p_h))

    algo = PairTradingAlgorithm(lookback_period=20, entry_threshold=1.5, exit_threshold=0.8)
    result = run_pair_backtest(
        algo,
        dominant_bars,
        hedge_bars,
        initial_cash=10_000.0,
        fee_rate=0.001,
        slippage_rate=0.0,
        rebalance_fraction=0.25,
        hedge_ratio=1.0,
    )

    # Initial deployment produces 2 trades.
    # Entry rebalance produces 2 trades (sell hedge, buy dominant).
    # Exit rebalance upon close_spread MUST produce unwinding trades (sell dominant, buy hedge).
    assert len(result.trades) >= 6, (
        f"Spot pair trading did not unwind rebalance on close_spread! Trades={len(result.trades)}"
    )


def test_perp_pair_backtest_terminal_liquidation():
    """Verify that open positions at end-of-test are liquidated with fees & slippage deducted."""
    dominant_bars = []
    hedge_bars = []
    for index in range(35):
        t = index * 3600
        p_d = 100.0
        p_h = 100.0 if index < 25 else 130.0  # open position and leave it open until end
        dominant_bars.append(_make_bar("BTCUSDT", t, p_d))
        hedge_bars.append(_make_bar("ETHUSDT", t, p_h))

    algo = PairTradingAlgorithm(lookback_period=20, entry_threshold=1.5, exit_threshold=0.5)
    fee_rate = 0.001
    slippage_rate = 0.001
    result = run_perp_pair_backtest(
        algo,
        dominant_bars,
        hedge_bars,
        initial_cash=10_000.0,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        position_fraction=0.5,
        liquidate_on_end=True,
    )
    # Positions must be zeroed upon terminal liquidation
    assert hasattr(result, "liquidated_equity")
    assert hasattr(result, "marked_equity")
    assert result.liquidated_equity < result.marked_equity, (
        f"Liquidated equity ({result.liquidated_equity}) should be lower than marked equity ({result.marked_equity}) due to exit fees/slippage"
    )
    # Closing trades must be recorded
    exit_trades = [t for t in result.trades if t.timestamp == dominant_bars[-1]["timestamp"]]
    assert len(exit_trades) >= 2, "Expected terminal liquidation trades for both legs"


def test_perp_pair_backtest_funding_tracking():
    """Verify that funding payments/receipts are tracked explicitly on PairBacktestResult."""
    dominant_bars = []
    hedge_bars = []
    for index in range(35):
        t = index * 3600
        p_d = 100.0
        p_h = 100.0 if index < 25 else 130.0
        dominant_bars.append(_make_bar("BTCUSDT", t, p_d))
        hedge_bars.append(_make_bar("ETHUSDT", t, p_h))

    algo = PairTradingAlgorithm(lookback_period=20, entry_threshold=1.5, exit_threshold=0.5)
    # Long dominant, Short hedge.
    # At timestamp 30*3600: dominant pays 0.01 (positive rate), hedge receives 0.01 (positive rate for short)
    funding_rates = {30 * 3600: (0.001, 0.001)}
    result = run_perp_pair_backtest(
        algo,
        dominant_bars,
        hedge_bars,
        initial_cash=10_000.0,
        funding_rates=funding_rates,
    )
    assert hasattr(result, "total_funding")
    assert hasattr(result, "total_funding_paid")
    assert hasattr(result, "total_funding_received")
    assert result.total_funding_paid > 0
    assert result.total_funding_received > 0

