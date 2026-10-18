from traderbot.hyperliquid.market_data import (
    fetch_hyperliquid_perp_coins,
    hyperliquid_perp_is_delisted,
)


def test_stg_is_delisted_on_hyperliquid():
    assert hyperliquid_perp_is_delisted("stg") is True


def test_delisted_coins_excluded_from_active_universe():
    active = fetch_hyperliquid_perp_coins(include_delisted=False)
    all_coins = fetch_hyperliquid_perp_coins(include_delisted=True)
    assert "STG" not in active
    assert "STG" in all_coins
    assert "BTC" in active
