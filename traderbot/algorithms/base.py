from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, Literal

SignalAction = Literal["buy", "sell", "hold"]

# Same keys as :func:`traderbot.markets.market_data.ohlc_rows` and export CSV rows.
Bar = Mapping[str, Any]


class Algorithm(ABC):
    """Pure strategy logic: one bar in, one signal out. Shared by live traders and backtests."""

    name = "algorithm"

    def reset(self) -> None:
        """Clear state before a new backtest run or bot session."""

    def sync_open_position(self, in_position: bool) -> None:
        """Align internal flags when live inventory diverges from strategy state."""

    @abstractmethod
    def on_bar(self, bar: Bar) -> SignalAction:
        """Called once per candle, oldest to newest."""
