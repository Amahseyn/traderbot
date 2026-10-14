from traderbot.algorithms.strategies.grid_trading import GridTradingAlgorithm
from traderbot.backtesting import run_backtest


def _bars(closes: list[float]) -> list[dict]:
    return [
        {
            "symbol": "BTCIRT",
            "resolution": "60",
            "timestamp": index * 3600,
            "datetime_utc": "",
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1.0,
        }
        for index, close in enumerate(closes)
    ]


def test_grid_trading_buys_on_dip_and_sells_on_take_profit():
    anchor = 100.0
    closes = [anchor, anchor, anchor * 0.95, anchor * 0.94, anchor * 0.96, anchor * 1.02]
    algo = GridTradingAlgorithm(grid_low_pct=-0.08, grid_high_pct=0.04, grid_levels=4, take_profit_pct=0.01)
    actions = [algo.on_bar(bar) for bar in _bars(closes)]
    assert "buy" in actions
    assert "sell" in actions


def test_grid_backtest_runs():
    anchor = 50.0
    closes = [anchor + (index % 7 - 3) * 0.4 for index in range(40)]
    result = run_backtest(GridTradingAlgorithm(), _bars(closes), initial_cash=5_000.0)
    assert result.final_equity > 0
