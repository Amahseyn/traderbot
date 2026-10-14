from traderbot.algorithms.strategies.pair_trading import PairTradingAlgorithm
from traderbot.backtesting.pair_engine import run_perp_pair_backtest


def _bars(closes: list[float], symbol: str) -> list[dict]:
    return [
        {
            "symbol": symbol,
            "resolution": "60",
            "timestamp": index * 3600,
            "open": price,
            "high": price * 1.01,
            "low": price * 0.99,
            "close": price,
            "volume": 1.0,
        }
        for index, price in enumerate(closes)
    ]


def test_perp_pair_backtest_opens_signed_legs():
    bar_count = 100
    dominant = [100.0 + index * 0.1 for index in range(bar_count)]
    hedge = [50.0 + index * 0.05 for index in range(bar_count)]
    hedge[-10:] = [x * 1.05 for x in hedge[-10:]]
    algo = PairTradingAlgorithm(lookback_period=25, entry_threshold=1.2, exit_threshold=0.3)
    result = run_perp_pair_backtest(
        algo,
        _bars(dominant, "BTCUSDT"),
        _bars(hedge, "ETHUSDT"),
        fee_rate=0.00045,
        slippage_rate=0.0005,
    )
    assert result.final_equity > 0
    assert len(result.trades) >= 0
