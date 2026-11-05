from __future__ import annotations

from typing import Any, Literal

import numpy as np

from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.algorithms.pair_trading.sizing import PairSizingModel
from traderbot.algorithms.pair_trading.spread import spread_z_score_from_closes, SpreadSnapshot
from traderbot.algorithms.pair_trading.state import PairLeggingPolicy, PairStateManager, PairTradingState

PairSignal = Literal["hold", "long_spread", "short_spread", "close_spread"]


class PairTradingAlgorithm(Algorithm):
    """
    Two-asset stat-arb on aligned bars (``hedge_close`` on each bar).

    Supports:
      - Validated cointegration model: Spread = log(A) - alpha - beta * log(B)
      - Causal rolling statistics, entry/exit thresholds, and stop-loss limits
      - Direct instantiation from Pair Discovery Engine candidates
      - Backward compatibility with legacy Hummingbot cumulative-return model

    Use :meth:`pair_signal` / :func:`traderbot.backtesting.pair_engine.run_perp_pair_backtest`;
    :meth:`on_bar` always returns ``hold`` (single-asset backtests are not applicable).
    """

    name = "pair_trading"

    def __init__(
        self,
        *,
        lookback_period: int = 60,
        entry_threshold: float = 2.0,
        exit_threshold: float = 0.5,
        stop_threshold: float = 4.0,
        max_holding_bars: int | None = None,
        symbol_a: str | None = None,
        symbol_b: str | None = None,
        hedge_ratio: float = 1.0,
        intercept: float = 0.0,
        spread_model: Literal["cointegration", "legacy"] = "cointegration",
        rolling_ols: bool = False,
        sizing_model: PairSizingModel = "hedge_ratio",
        qualification_status: str = "qualified",
        confidence: dict[str, Any] | None = None,
        legging_policy: PairLeggingPolicy = "immediate_flatten",
    ):
        if lookback_period < 5:
            raise ValueError("lookback_period must be >= 5")
        if entry_threshold <= exit_threshold:
            raise ValueError("entry_threshold must be greater than exit_threshold")
        if stop_threshold <= entry_threshold:
            raise ValueError("stop_threshold must be greater than entry_threshold")
        if max_holding_bars is not None and max_holding_bars <= 0:
            raise ValueError("max_holding_bars must be positive")
        if hedge_ratio <= 0:
            raise ValueError("hedge_ratio must be positive")

        self.lookback_period = lookback_period
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.stop_threshold = stop_threshold
        self.max_holding_bars = max_holding_bars
        self.symbol_a = symbol_a
        self.symbol_b = symbol_b
        self.hedge_ratio = hedge_ratio
        self.intercept = intercept
        self.spread_model = spread_model
        self.rolling_ols = rolling_ols
        self.sizing_model = sizing_model
        self.qualification_status = qualification_status
        self.confidence = confidence or {}

        self.state_manager = PairStateManager(
            qualification_status=qualification_status,
            legging_policy=legging_policy,
        )

        self._dominant_closes: list[float] = []
        self._hedge_closes: list[float] = []
        self._spread_position: Literal["flat", "long_spread", "short_spread"] = "flat"
        self.last_z_score: float | None = None
        self.last_spread_pct: float | None = None
        self.last_spread_mean: float | None = None
        self.last_spread_std: float | None = None
        self.last_snapshot: SpreadSnapshot | None = None

    @classmethod
    def from_ranked_pair(
        cls,
        ranked_pair: Any,
        *,
        lookback_period: int | None = None,
        entry_threshold: float = 2.0,
        exit_threshold: float = 0.5,
        stop_threshold: float = 4.0,
        max_holding_bars: int | None = None,
        sizing_model: PairSizingModel = "hedge_ratio",
        spread_model: Literal["cointegration", "legacy"] = "cointegration",
        **kwargs: Any,
    ) -> PairTradingAlgorithm:
        """
        Create a PairTradingAlgorithm configured from a Pair Discovery RankedPairResult.
        """
        symbol_a = (
            getattr(ranked_pair, "symbol_a", None)
            or (ranked_pair.get("symbol_a") if isinstance(ranked_pair, dict) else None)
        )
        symbol_b = (
            getattr(ranked_pair, "symbol_b", None)
            or (ranked_pair.get("symbol_b") if isinstance(ranked_pair, dict) else None)
        )
        hedge_ratio = float(
            getattr(ranked_pair, "hedge_ratio", 1.0)
            if hasattr(ranked_pair, "hedge_ratio")
            else (ranked_pair.get("hedge_ratio", 1.0) if isinstance(ranked_pair, dict) else 1.0)
        )
        intercept = float(
            getattr(ranked_pair, "intercept", 0.0)
            if hasattr(ranked_pair, "intercept")
            else (ranked_pair.get("intercept", 0.0) if isinstance(ranked_pair, dict) else 0.0)
        )
        qual_status = str(
            getattr(ranked_pair, "qualification_status", "qualified")
            if hasattr(ranked_pair, "qualification_status")
            else (ranked_pair.get("qualification_status", "qualified") if isinstance(ranked_pair, dict) else "qualified")
        )
        half_life = (
            getattr(ranked_pair, "half_life_bars", None)
            if hasattr(ranked_pair, "half_life_bars")
            else (ranked_pair.get("half_life_bars") if isinstance(ranked_pair, dict) else None)
        )

        effective_lookback = lookback_period
        if effective_lookback is None:
            if half_life is not None and half_life > 0:
                effective_lookback = max(20, int(round(half_life * 3.0)))
            else:
                effective_lookback = 60

        effective_max_holding = max_holding_bars
        if effective_max_holding is None and half_life is not None and half_life > 0:
            effective_max_holding = max(10, int(round(half_life * 4.0)))

        confidence = {
            "cointegration_pvalue": getattr(ranked_pair, "cointegration_pvalue", None),
            "adf_statistic": getattr(ranked_pair, "adf_statistic", None),
            "half_life_bars": half_life,
            "pair_quality_score": getattr(ranked_pair, "pair_quality_score", None),
        }

        return cls(
            lookback_period=effective_lookback,
            entry_threshold=entry_threshold,
            exit_threshold=exit_threshold,
            stop_threshold=stop_threshold,
            max_holding_bars=effective_max_holding,
            symbol_a=symbol_a,
            symbol_b=symbol_b,
            hedge_ratio=hedge_ratio,
            intercept=intercept,
            spread_model=spread_model,
            sizing_model=sizing_model,
            qualification_status=qual_status,
            confidence=confidence,
            **kwargs,
        )

    @property
    def state(self) -> PairTradingState:
        return self.state_manager.state

    @property
    def holding_bars(self) -> int:
        return self.state_manager.holding_bars

    def reset(self) -> None:
        self._dominant_closes.clear()
        self._hedge_closes.clear()
        self._spread_position = "flat"
        self.last_z_score = None
        self.last_spread_pct = None
        self.last_spread_mean = None
        self.last_spread_std = None
        self.last_snapshot = None
        self.state_manager.reset()

    def sync_open_position(self, in_position: bool) -> None:
        if not in_position:
            self._spread_position = "flat"
            if self.state_manager.state == "OPEN":
                self.state_manager.confirm_exit_filled()

    def update_qualification(self, qualification_status: str) -> None:
        self.qualification_status = qualification_status
        self.state_manager.update_qualification(qualification_status)

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

        self.state_manager.on_bar(len(self._dominant_closes), self.lookback_period)

        snapshot = spread_z_score_from_closes(
            np.asarray(self._dominant_closes, dtype=float),
            np.asarray(self._hedge_closes, dtype=float),
            lookback_period=self.lookback_period,
            model=self.spread_model,
            hedge_ratio=self.hedge_ratio,
            intercept=self.intercept,
            rolling_ols=self.rolling_ols,
        )
        if snapshot is None:
            return "hold"

        self.last_snapshot = snapshot
        self.last_z_score = snapshot.z_score
        self.last_spread_pct = snapshot.spread_pct
        self.last_spread_mean = snapshot.spread_mean
        self.last_spread_std = snapshot.spread_std
        z_score = snapshot.z_score

        # -------------------------------------------------------------
        # Cointegration-based Spread Model
        # Spread = log(A) - alpha - beta * log(B)
        # -------------------------------------------------------------
        if self.spread_model == "cointegration":
            if self._spread_position == "long_spread":
                # Long A / Short B: entered when spread was low (Z <= -entry)
                # Exit when spread mean-reverts up to -exit_threshold
                # Stop when spread expands further down to -stop_threshold
                should_exit = False
                exit_reason = "reversion"
                if z_score >= -self.exit_threshold or z_score >= self.entry_threshold:
                    should_exit = True
                    exit_reason = "reversion"
                elif z_score <= -self.stop_threshold:
                    should_exit = True
                    exit_reason = "stop_loss"
                elif self.max_holding_bars is not None and self.state_manager.holding_bars >= self.max_holding_bars:
                    should_exit = True
                    exit_reason = "max_holding_bars"
                elif self.state_manager.qualification_status == "rejected":
                    should_exit = True
                    exit_reason = "qualification_lost"

                if should_exit:
                    self._spread_position = "flat"
                    self.state_manager.trigger_exit(reason=exit_reason)
                    self.state_manager.confirm_exit_filled()
                    return "close_spread"
                return "hold"

            if self._spread_position == "short_spread":
                # Short A / Long B: entered when spread was high (Z >= +entry)
                # Exit when spread mean-reverts down to +exit_threshold
                # Stop when spread expands further up to +stop_threshold
                should_exit = False
                exit_reason = "reversion"
                if z_score <= self.exit_threshold or z_score <= -self.entry_threshold:
                    should_exit = True
                    exit_reason = "reversion"
                elif z_score >= self.stop_threshold:
                    should_exit = True
                    exit_reason = "stop_loss"
                elif self.max_holding_bars is not None and self.state_manager.holding_bars >= self.max_holding_bars:
                    should_exit = True
                    exit_reason = "max_holding_bars"
                elif self.state_manager.qualification_status == "rejected":
                    should_exit = True
                    exit_reason = "qualification_lost"

                if should_exit:
                    self._spread_position = "flat"
                    self.state_manager.trigger_exit(reason=exit_reason)
                    self.state_manager.confirm_exit_filled()
                    return "close_spread"
                return "hold"

            # Flat: evaluate entry
            if not self.state_manager.can_enter():
                return "hold"

            # Low spread: Asset A is undervalued relative to B -> Long Spread (Long A, Short B)
            if -self.stop_threshold < z_score <= -self.entry_threshold:
                if self.state_manager.trigger_entry("long_spread"):
                    self._spread_position = "long_spread"
                    self.state_manager.confirm_entry_filled(leg_a_filled=True, leg_b_filled=True)
                    return "long_spread"

            # High spread: Asset A is overvalued relative to B -> Short Spread (Short A, Long B)
            if self.stop_threshold > z_score >= self.entry_threshold:
                if self.state_manager.trigger_entry("short_spread"):
                    self._spread_position = "short_spread"
                    self.state_manager.confirm_entry_filled(leg_a_filled=True, leg_b_filled=True)
                    return "short_spread"

            return "hold"

        # -------------------------------------------------------------
        # Legacy Hummingbot Model
        # (Preserved for backward compatibility)
        # -------------------------------------------------------------
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

