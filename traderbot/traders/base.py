from __future__ import annotations

from abc import ABC, abstractmethod

from traderbot.client import NobitexClient


class Trader(ABC):
    """One strategy: implement ``step`` and plug it into a :class:`~traderbot.bots.base.Bot`."""

    name: str = "trader"

    def __init__(self, client: NobitexClient):
        self.client = client

    @abstractmethod
    def step(self) -> None:
        """Single iteration (poll market, place/cancel orders, etc.)."""
