from traderbot.algorithms.strategies.funding_carry import FundingCarryAlgorithm
from traderbot.backtesting.funding_carry_engine import run_funding_carry_backtest


def test_funding_carry_collects_positive_funding():
    price_bars = [
        {"timestamp": index * 3600, "close": 100.0 + index * 0.01}
        for index in range(50)
    ]
    funding_events = [
        {"time_unix_seconds": index * 3600, "funding_rate": 0.0001}
        for index in range(1, 40)
    ]
    algo = FundingCarryAlgorithm(entry_funding_rate=0.00005, exit_funding_rate=0.00002)
    result = run_funding_carry_backtest(algo, price_bars, funding_events, fee_rate=0.00045)
    assert result.total_funding_pnl > 0
    assert result.trade_count >= 1
