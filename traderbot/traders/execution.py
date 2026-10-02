from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from traderbot.algorithms.base import SignalAction

ExecutionMode = Literal["paper", "live"]


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    """
    Gates order placement before :meth:`AlgorithmTrader.on_signal`.

    Default is paper mode: signals invoke :meth:`AlgorithmTrader.on_paper_signal`
    instead of live ``on_signal`` (which remains an override hook for real orders).
    """

    mode: ExecutionMode = "paper"
    allow_buy: bool = True
    allow_sell: bool = True
    kill_switch: bool = False

    @classmethod
    def paper_only(cls) -> ExecutionPolicy:
        return cls(mode="paper")

    @classmethod
    def live(cls, *, allow_buy: bool = True, allow_sell: bool = True) -> ExecutionPolicy:
        return cls(mode="live", allow_buy=allow_buy, allow_sell=allow_sell)

    def permits(self, action: SignalAction) -> bool:
        if action == "hold" or self.kill_switch:
            return False
        if action == "buy" and not self.allow_buy:
            return False
        if action == "sell" and not self.allow_sell:
            return False
        return True
