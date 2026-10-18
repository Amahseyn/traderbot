from traderbot.utils.trading_costs import DEFAULT_SLIPPAGE_RATE, DEFAULT_TRADE_FEE_RATE


def test_default_fee_matches_hyperliquid_base_taker():
    assert DEFAULT_TRADE_FEE_RATE == 0.00045


def test_default_slippage_is_zero_for_hyperliquid_style_backtests():
    assert DEFAULT_SLIPPAGE_RATE == 0.0


def test_hyperliquid_backtest_costs():
    from traderbot.utils.trading_costs import backtest_cost_rates

    fee, slip = backtest_cost_rates("hyperliquid", fee_role="taker")
    assert fee == 0.00045
    assert slip == 0.0
