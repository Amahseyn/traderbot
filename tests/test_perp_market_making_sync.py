from traderbot.algorithms.strategies.perp_market_making import PerpMarketMakingAlgorithm
from traderbot.backtesting.engine import run_backtest


def _bar(ts: int, o: float, h: float, l: float, c: float) -> dict:
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": 1.0}


def test_sync_open_position_aligns_after_warmup_replay() -> None:
    algo = PerpMarketMakingAlgorithm(half_spread_pct=0.01, vol_spread_mult=0.0, atr_period=1)
    bar = {"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0}
    for _ in range(4):
        algo.on_bar(bar)
    algo.sync_open_position(True)
    algo.on_bar(bar)
    assert [q.side for q in algo.quotes()] == ["sell"]
    algo.sync_open_position(False)
    # Paper is flat — next bar should quote a bid, not a spurious exit from warmup state.
    algo.on_bar(bar)
    assert [q.side for q in algo.quotes()] == ["buy"]


def test_quotes_use_previous_bar_and_need_trade_through() -> None:
    algo = PerpMarketMakingAlgorithm(
        half_spread_pct=0.01, vol_spread_mult=0.0, atr_period=1, stop_loss_pct=0.0, trend_guard=False
    )
    flat = [_bar(i, 100.0, 100.2, 99.8, 100.0) for i in range(5)]
    # Bid rests at 99.0 from the previous close; a low of exactly 99.0 does not trade through.
    touch = _bar(5, 100.0, 100.0, 99.0, 99.5)
    through = _bar(6, 99.5, 99.6, 98.0, 98.5)
    result = run_backtest(algo, flat + [touch, through], fee_rate=0.00045, slippage_rate=0.0005)
    buys = [t for t in result.trades if t.action == "buy"]
    assert len(buys) == 1
    # Bid was placed at bar 5's close (99.5) * (1 - 1%) and filled at that price, maker fee.
    assert buys[0].price == 99.5 * 0.99
    assert buys[0].liquidity == "maker"
    assert abs(buys[0].fee - buys[0].size * buys[0].price * 0.00015) < 1e-9
    assert result.maker_fee_rate == 0.00015


def test_no_fill_when_quote_is_never_traded_through() -> None:
    algo = PerpMarketMakingAlgorithm(half_spread_pct=0.01, vol_spread_mult=0.0, atr_period=1)
    bars = [_bar(i, 100.0, 100.3, 99.7, 100.0) for i in range(50)]
    result = run_backtest(algo, bars, fee_rate=0.00045)
    assert result.trades == []


def test_round_trip_captures_spread_minus_maker_fees() -> None:
    algo = PerpMarketMakingAlgorithm(
        half_spread_pct=0.005, vol_spread_mult=0.0, atr_period=1, stop_loss_pct=0.0, min_profit_pct=0.0
    )
    bars = [_bar(i, 100.0, 100.1, 99.9, 100.0) for i in range(5)]
    bars.append(_bar(5, 100.0, 100.0, 99.0, 99.6))  # bid 99.5 traded through -> long
    bars.append(_bar(6, 99.6, 100.5, 99.6, 100.4))  # ask 99.6*1.005=100.098 traded through -> flat
    result = run_backtest(algo, bars, fee_rate=0.00045, initial_cash=10_000.0)
    assert [t.action for t in result.trades] == ["buy", "sell"]
    assert all(t.liquidity == "maker" for t in result.trades)
    assert result.final_equity > 10_000.0


def test_stop_protects_inventory_with_taker_cost() -> None:
    algo = PerpMarketMakingAlgorithm(half_spread_pct=0.005, vol_spread_mult=0.0, atr_period=1, stop_loss_pct=0.01)
    bars = [_bar(i, 100.0, 100.1, 99.9, 100.0) for i in range(5)]
    bars.append(_bar(5, 100.0, 100.0, 99.0, 99.6))
    bars.append(_bar(6, 99.6, 99.6, 97.0, 97.5))  # stop at 99.5*0.99 = 98.505
    result = run_backtest(algo, bars, fee_rate=0.00045, slippage_rate=0.0005)
    exit_trade = result.trades[-1]
    assert exit_trade.reason == "stop_loss"
    assert exit_trade.liquidity == "taker"
    assert abs(exit_trade.price - 99.5 * 0.99 * (1 - 0.0005)) < 1e-9


def test_shorts_only_when_allowed_and_not_on_nobitex() -> None:
    bars = [_bar(i, 100.0, 100.1, 99.9, 100.0) | {"symbol": "BTCUSDT"} for i in range(5)]
    bars.append(_bar(5, 100.0, 101.0, 99.95, 100.0) | {"symbol": "BTCUSDT"})
    algo = PerpMarketMakingAlgorithm(half_spread_pct=0.005, vol_spread_mult=0.0, atr_period=1, allow_short=True)
    result = run_backtest(algo, bars, fee_rate=0.00045)
    assert result.trades and result.trades[0].action == "sell" and result.trades[0].position_after < 0
    irt = [dict(bar, symbol="BTCIRT") for bar in bars]
    algo = PerpMarketMakingAlgorithm(half_spread_pct=0.005, vol_spread_mult=0.0, atr_period=1, allow_short=True)
    assert run_backtest(algo, irt, fee_rate=0.0035).trades == []
