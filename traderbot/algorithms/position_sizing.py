"""Entry sizing for signal strategies that historically traded all-in.

``target_exposure`` caps each buy at a fraction of equity; ``1.0`` (the default on
every strategy) keeps the legacy all-in behavior so existing backtests stay identical.
Sells always close risk: the position is taken flat regardless of the fraction.
"""

from __future__ import annotations

from traderbot.algorithms.base import OrderSize, SignalAction

ALL_IN_EXPOSURE = 1.0


def validate_target_exposure(target_exposure: float) -> float:
    value = float(target_exposure)
    if not 0.0 < value <= ALL_IN_EXPOSURE:
        raise ValueError("target_exposure must be in (0, 1]")
    return value


def entry_order_size(target_exposure: float, action: SignalAction) -> OrderSize | None:
    """Sizing for a non-hold signal, or ``None`` under the legacy all-in / all-out behavior."""
    if target_exposure >= ALL_IN_EXPOSURE:
        return None
    return OrderSize(target_exposure=target_exposure if action == "buy" else 0.0)


MAX_TRANCHE_EXPOSURE = 1.0 + 1e-9


class EntryTranches:
    """Entry sizing + tranche cadence for strategies that may add to the same position.

    ``max_tranches=1`` (the default) keeps the single-position behavior: the first entry
    targets ``target_exposure`` equity, later entry signals are dropped, and sizes stay
    ``None`` (legacy all-in / all-out) so existing backtests remain identical. With
    ``max_tranches > 1`` — allowed only while ``target_exposure * max_tranches <= 1.0`` —
    a fresh entry signal adds another tranche once ``tranche_gap_bars`` bars passed since
    the last one; the ``k``-th tranche targets ``k * target_exposure`` equity. Sells exit
    flat and reset the tranche count.
    """

    def __init__(self, *, target_exposure: float = ALL_IN_EXPOSURE, max_tranches: int = 1,
                 tranche_gap_bars: int = 0):
        self.target_exposure = validate_target_exposure(target_exposure)
        self.max_tranches = int(max_tranches)
        if self.max_tranches < 1:
            raise ValueError("max_tranches must be at least 1")
        if self.target_exposure * self.max_tranches > MAX_TRANCHE_EXPOSURE:
            raise ValueError("target_exposure * max_tranches must not exceed 1.0")
        self.tranche_gap_bars = int(tranche_gap_bars)
        if self.tranche_gap_bars < 0:
            raise ValueError("tranche_gap_bars must not be negative")
        self.tranches = 0
        self.bars_since_entry: int | None = None

    @property
    def partial(self) -> bool:
        """True when sizing differs from the legacy all-in / all-out behavior."""
        return self.target_exposure < ALL_IN_EXPOSURE or self.max_tranches > 1

    def reset(self) -> None:
        self.tranches = 0
        self.bars_since_entry = None

    def tick(self) -> None:
        if self.bars_since_entry is not None:
            self.bars_since_entry += 1

    def allows_entry(self) -> bool:
        """Whether this bar may accept another tranche (capacity + cadence gap)."""
        if self.tranches >= self.max_tranches:
            return False
        return self.bars_since_entry is None or self.bars_since_entry >= self.tranche_gap_bars

    def note_entry(self) -> OrderSize | None:
        """Sizing for an accepted entry; bumps the tranche count."""
        self.tranches += 1
        self.bars_since_entry = 0
        if not self.partial:
            return None
        return OrderSize(target_exposure=self.target_exposure * self.tranches)

    def repeat_entry(self) -> OrderSize | None:
        """Sizing for an entry signal emitted while blocked (gap or at capacity).

        Targets the current filled level, so the fill is a no-op; the legacy all-in
        behavior keeps the ``None`` size. The tranche count is not bumped.
        """
        if not self.partial:
            return None
        return OrderSize(target_exposure=self.target_exposure * max(self.tranches, 1))

    def note_exit(self) -> OrderSize | None:
        """Flat sizing for a sell, resetting the tranche state."""
        self.reset()
        if not self.partial:
            return None
        return OrderSize(target_exposure=0.0)
