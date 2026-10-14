from traderbot.utils.trading_costs import DEFAULT_SLIPPAGE_RATE, DEFAULT_TRADE_FEE_RATE


def test_default_fee_matches_hyperliquid_base_taker():
    assert DEFAULT_TRADE_FEE_RATE == 0.00045


def test_default_slippage():
    assert DEFAULT_SLIPPAGE_RATE == 0.0005
