from traderbot.algorithms.strategies.spot_grid import SpotGridAlgorithm
from traderbot.backtesting import run_backtest


def _bars(closes: list[float]) -> list[dict]:
    return [
        {
            "symbol": "BTCIRT",
            "resolution": "60",
            "timestamp": index * 3600,
            "open": price,
            "high": price * 1.02,
            "low": price * 0.98,
            "close": price,
            "volume": 1.0,
        }
        for index, price in enumerate(closes)
    ]


def test_spot_grid_buy_and_take_profit():
    algo = SpotGridAlgorithm(start_price=90.0, end_price=110.0, grid_count=5, take_profit_pct=0.02)
    bars = _bars([105.0, 108.0])
    assert algo.on_bar(bars[0]) == "buy"
    assert algo.on_bar(bars[1]) == "sell"


def test_spot_grid_backtest_produces_trades():
    prices = [100.0] * 5 + [98.0, 96.0, 95.0, 97.0, 100.0, 102.0, 104.0]
    bars = _bars(prices)
    algo = SpotGridAlgorithm(start_price=90.0, end_price=110.0, grid_count=6, take_profit_pct=0.015)
    result = run_backtest(algo, bars, initial_cash=10_000.0, fee_rate=0.001)
    assert result.final_equity > 0
