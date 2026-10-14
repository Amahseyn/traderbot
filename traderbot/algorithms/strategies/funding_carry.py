from __future__ import annotations

from typing import Literal

from traderbot.algorithms.base import Algorithm, Bar, SignalAction

FundingSignal = Literal["hold", "enter_short", "exit"]


class FundingCarryAlgorithm(Algorithm):
    """
    Collect positive perp funding by holding a short when the hourly rate is elevated (Hyperliquid only).
    """

    name = "funding_carry"

    def __init__(
        self,
        *,
        entry_funding_rate: float = 0.00004,
        exit_funding_rate: float = 0.00001,
        position_fraction: float = 0.5,
    ):
        if entry_funding_rate <= exit_funding_rate:
            raise ValueError("entry_funding_rate must exceed exit_funding_rate")
        self.entry_funding_rate = entry_funding_rate
        self.exit_funding_rate = exit_funding_rate
        self.position_fraction = position_fraction
        self._in_short = False

    def reset(self) -> None:
        self._in_short = False

    def on_bar(self, bar: Bar) -> SignalAction:
        return "hold"

    def on_funding(self, funding_rate: float) -> FundingSignal:
        if not self._in_short and funding_rate >= self.entry_funding_rate:
            self._in_short = True
            return "enter_short"
        if self._in_short and funding_rate <= self.exit_funding_rate:
            self._in_short = False
            return "exit"
        return "hold"
