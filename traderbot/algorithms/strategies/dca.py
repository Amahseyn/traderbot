"""Dollar-cost averaging: buy a fixed cash amount every N bars (benchmark vs lump sum)."""

from __future__ import annotations

from traderbot.algorithms.base import Algorithm, Bar, OrderSize, SignalAction


class DcaAlgorithm(Algorithm):
    """Every ``dca_interval_bars`` bars spend ``1 / dca_order_count`` of the initial cash, until
    ``dca_order_count`` orders are placed; never sells. Compare with a lump-sum buy of the same
    cash on the first bar (``build_dca_lump_sum_comparison``)."""

    name = "dca"
    uses_position_sizing = True

    def __init__(self, *, dca_interval_bars = 24, dca_order_count = 10):
        if dca_interval_bars < 1:
            raise ValueError("dca_interval_bars must be >= 1")
        if dca_order_count < 1:
            raise ValueError("dca_order_count must be >= 1")
        self.dca_interval_bars = dca_interval_bars
        self.dca_order_count = dca_order_count
        self.reset()

    def reset(self) -> None:
        self._bar_index = -1
        self._orders_placed = 0

    def order_size(self) -> OrderSize | None:
        return OrderSize(cash_fraction=1.0 / self.dca_order_count)

    def on_bar(self, bar: Bar) -> SignalAction:
        self._bar_index += 1
        if self._orders_placed >= self.dca_order_count:
            return "hold"
        if self._bar_index % self.dca_interval_bars == 0:
            self._orders_placed += 1
            return "buy"
        return "hold"
