from __future__ import annotations

from typing import Literal

from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.algorithms.pair_trading.spread import spread_z_score_from_closes

import numpy as np

PairSignal = Literal["hold", "long_spread", "short_spread", "close_spread"]


class PairTradingAlgorithm(Algorithm):
    """
    Two-asset stat-arb on aligned bars (``hedge_close`` on each bar).

    Use :meth:`pair_signal` / :func:`traderbot.backtesting.pair_engine.run_pair_backtest`;
    :meth:`on_bar` always returns ``hold`` (single-asset backtests are not applicable).
    """

    name = "pair_trading"

    def __init__(
        self,
        *,
        lookback_period: int = 60,
        entry_threshold: float = 2.0,
        exit_threshold: float = 0.5,
    ):
        if lookback_period < 5:
            raise ValueError("lookback_period must be >= 5")
        if entry_threshold <= exit_threshold:
            raise ValueError("entry_threshold must be greater than exit_threshold")
        self.lookback_period = lookback_period
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self._dominant_closes: list[float] = []
        self._hedge_closes: list[float] = []
        self._spread_position: Literal["flat", "long_spread", "short_spread"] = "flat"
        self.last_z_score: float | None = None
        self.last_spread_pct: float | None = None

    def reset(self) -> None:
        self._dominant_closes.clear()
        self._hedge_closes.clear()
        self._spread_position = "flat"
        self.last_z_score = None
        self.last_spread_pct = None

    def sync_open_position(self, in_position: bool) -> None:
        if not in_position:
            self._spread_position = "flat"

    def on_bar(self, bar: Bar) -> SignalAction:
        self.pair_signal(bar)
        return "hold"

    def pair_signal(self, bar: Bar) -> PairSignal:
        hedge_close = bar.get("hedge_close")
        if hedge_close is None:
            return "hold"
        dominant_close = float(bar["close"])
        self._dominant_closes.append(dominant_close)
        self._hedge_closes.append(float(hedge_close))

        snapshot = spread_z_score_from_closes(
            np.asarray(self._dominant_closes, dtype=float),
            np.asarray(self._hedge_closes, dtype=float),
            lookback_period=self.lookback_period,
        )
        if snapshot is None:
            return "hold"

        self.last_z_score = snapshot.z_score
        self.last_spread_pct = snapshot.spread_pct
        z_score = snapshot.z_score

        if self._spread_position == "long_spread":
            if abs(z_score) <= self.exit_threshold or z_score < -self.entry_threshold:
                self._spread_position = "flat"
                return "close_spread"
            return "hold"

        if self._spread_position == "short_spread":
            if abs(z_score) <= self.exit_threshold or z_score > self.entry_threshold:
                self._spread_position = "flat"
                return "close_spread"
            return "hold"

        if z_score > self.entry_threshold:
            self._spread_position = "long_spread"
            return "long_spread"
        if z_score < -self.entry_threshold:
            self._spread_position = "short_spread"
            return "short_spread"
        return "hold"
