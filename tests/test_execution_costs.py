from traderbot.markets.execution_costs import execution_cost_profile


def test_hyperliquid_maker_cheaper_than_taker():
    taker = execution_cost_profile("hyperliquid", fee_role="taker")
    maker = execution_cost_profile("hyperliquid", fee_role="maker")
    assert maker.fee_rate < taker.fee_rate


def test_nobitex_fees_higher_than_hyperliquid_taker():
    nobitex = execution_cost_profile("nobitex", fee_role="taker")
    hyperliquid = execution_cost_profile("hyperliquid", fee_role="taker")
    assert nobitex.fee_rate > hyperliquid.fee_rate
