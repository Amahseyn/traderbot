from __future__ import annotations

from traderbot.markets.exchange import LIVE_EXCHANGES

# Hummingbot-inspired strategies and which venues they support in traderbot.
STRATEGY_EXCHANGE_SUPPORT: dict[str, tuple[str, ...]] = {
    "pair_trading": ("nobitex", "hyperliquid"),
    "spot_grid": ("nobitex", "hyperliquid"),
    "funding_carry": ("hyperliquid",),
    "perp_market_making": ("hyperliquid",),
}

# Rule strategies from registry run on any OHLC series (CSV or live export).
RULE_STRATEGY_EXCHANGES: tuple[str, ...] = LIVE_EXCHANGES


def exchanges_for_strategy(strategy_id: str) -> tuple[str, ...]:
    return STRATEGY_EXCHANGE_SUPPORT.get(strategy_id, RULE_STRATEGY_EXCHANGES)


def strategy_supported_on(strategy_id: str, exchange: str) -> bool:
    return exchange in exchanges_for_strategy(strategy_id)
