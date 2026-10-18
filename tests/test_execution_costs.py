from traderbot.markets.execution_costs import (
    HYPERLIQUID_PERP_MAKER_FEE,
    HYPERLIQUID_PERP_TAKER_FEE,
    execution_cost_profile,
)


def test_hyperliquid_maker_cheaper_than_taker():
    taker = execution_cost_profile("hyperliquid", fee_role="taker")
    maker = execution_cost_profile("hyperliquid", fee_role="maker")
    assert maker.fee_rate < taker.fee_rate
    assert taker.fee_rate == HYPERLIQUID_PERP_TAKER_FEE
    assert maker.fee_rate == HYPERLIQUID_PERP_MAKER_FEE
    assert taker.slippage_rate == 0.0005
    assert maker.slippage_rate == 0.0


def test_nobitex_fees_higher_than_hyperliquid_taker():
    nobitex = execution_cost_profile("nobitex", fee_role="taker")
    hyperliquid = execution_cost_profile("hyperliquid", fee_role="taker")
    assert nobitex.fee_rate > hyperliquid.fee_rate
