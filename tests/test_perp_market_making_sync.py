from traderbot.algorithms.strategies.perp_market_making import PerpMarketMakingAlgorithm


def test_sync_open_position_aligns_after_warmup_replay() -> None:
    algo = PerpMarketMakingAlgorithm(half_spread_pct=0.01)
    bar = {"open": 100.0, "high": 100.5, "low": 98.0, "close": 100.0}
    assert algo.on_bar(bar) == "buy"
    algo.sync_open_position(False)
    # Paper is flat — next bar should allow a buy, not a spurious sell from warmup state.
    assert algo.on_bar(bar) == "buy"
