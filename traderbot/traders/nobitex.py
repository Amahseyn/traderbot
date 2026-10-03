from __future__ import annotations

from traderbot.nobitex.client import NobitexClient
from traderbot.traders.base import Trader


class NobitexTrader(Trader):
    """Trader wired to Nobitex; subclass and override ``step``."""

    @classmethod
    def from_env(cls) -> NobitexTrader:
        return cls(NobitexClient.from_env())
