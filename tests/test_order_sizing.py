from traderbot.algorithms.base import OrderSize
from traderbot.algorithms.strategies.dca import DcaAlgorithm
from traderbot.algorithms.strategies.spot_grid import grid_price_bounds_from_bars
from traderbot.algorithms.registry import build_strategy_kwargs_for_bars, algorithm_for_id
from traderbot.backtesting.engine import run_backtest
from traderbot.terminal.paper_portfolio import PaperPortfolio
from traderbot.traders.order_sizing import buy_quote_spend, sell_base_amount


def test_grid_price_bounds_from_bars():
    bars = [{"close": 100.0}, {"close": 110.0}]
    low, high = grid_price_bounds_from_bars(bars)
    assert low < 100.0
    assert high > 110.0


def test_build_strategy_kwargs_instantiates_spot_grid():
    bars = [{"close": 100.0 + index} for index in range(30)]
    kwargs = build_strategy_kwargs_for_bars("spot_grid", bars)
    algo = algorithm_for_id("spot_grid", **kwargs)
    assert algo.start_price < algo.end_price


def test_dca_paper_partial_matches_fraction():
    portfolio = PaperPortfolio(quote_cash=10_000.0, quote_currency="usdt")
    size = OrderSize(cash_fraction=0.1)
    fill = portfolio.apply_fill("buy", 100.0, order_size=size)
    assert fill["filled"] is True
    assert portfolio.quote_cash == 9_000.0
    assert portfolio.base_amount > 0


def test_partial_sell_keeps_inventory():
    spend = buy_quote_spend(
        OrderSize(target_exposure=0.5),
        cash=5_000.0,
        position=1.0,
        fill_price=100.0,
        initial_cash=10_000.0,
    )
    assert spend > 0
    sold = sell_base_amount(
        OrderSize(target_exposure=0.25),
        cash=0.0,
        position=1.0,
        fill_price=100.0,
    )
    assert 0 < sold < 1.0


def test_dca_backtest_uses_cash_fraction():
    bars = [
        {
            "timestamp": index,
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "volume": 1.0,
        }
        for index in range(30)
    ]
    algo = DcaAlgorithm(dca_interval_bars=5, dca_order_count=10)
    result = run_backtest(algo, bars, initial_cash=10_000.0)
    buys = [trade for trade in result.trades if trade.action == "buy"]
    assert len(buys) == 6
    assert buys[0].cash_before - buys[0].cash_after == 1_000.0
