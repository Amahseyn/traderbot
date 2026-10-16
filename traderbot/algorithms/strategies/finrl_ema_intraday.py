"""FinRL-Trading intraday preset: EMA 12/48 crossover (Hyperliquid 1m/5m research default)."""

from traderbot.algorithms.strategies.ema_cross import EmaCrossAlgorithm


class FinrlEmaIntradayAlgorithm(EmaCrossAlgorithm):
    name = "finrl_ema_intraday"

    def __init__(self, *, fast: int = 12, slow: int = 48, price_confirm: bool = False):
        super().__init__(fast=fast, slow=slow, price_confirm=price_confirm)
