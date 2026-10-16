"""Combine multiple :class:`~traderbot.algorithms.base.Algorithm` children into one signal stream."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from traderbot.algorithms.base import Algorithm, Bar, SignalAction


def _default_member_factory(strategy_id: str, **kwargs: Any) -> Algorithm:
    from traderbot.algorithms.registry import algorithm_for_id

    return algorithm_for_id(strategy_id, **kwargs)

ENSEMBLE_ENTRY_RULES = ("all", "majority", "primary")
ENSEMBLE_EXIT_RULES = ("any", "all", "primary")

# (strategy_id, kwargs overrides) — tuned for noisy 1m bars; override via CLI namespace where shared.
ENSEMBLE_PRESETS: dict[str, list[tuple[str, dict[str, Any]]]] = {
    "1m_scalp_trend": [
        (
            "scalp_dip",
            {
                "dip_lookback_bars": 12,
                "dip_pct": 0.003,
                "take_profit_pct": 0.006,
                "stop_loss_pct": 0.004,
                "scalp_position_fraction": 1.0,
            },
        ),
        (
            "rsi_trend",
            {
                "period": 7,
                "trend_filter_period": 21,
                "rsi_trend_entry": 52.0,
                "rsi_trend_exit": 48.0,
            },
        ),
    ],
    "1m_pattern_ma": [
        ("chart_patterns", {"swing_window_bars": 2, "pattern_score_threshold": 0.3}),
        ("ema_cross", {"fast": 8, "slow": 21, "price_confirm": True}),
    ],
    "1m_ml_trend": [
        (
            "online_logistic",
            {
                "lookback_bars": 24,
                "ml_horizon_bars": 3,
                "ml_warmup_samples": 80,
                "ml_buy_threshold": 0.56,
                "ml_sell_threshold": 0.44,
            },
        ),
        (
            "rsi_trend",
            {"period": 10, "trend_filter_period": 34, "rsi_trend_entry": 54.0, "rsi_trend_exit": 46.0},
        ),
    ],
    "intraday_trend_stack": [
        ("rsi_trend", {"period": 14, "trend_filter_period": 50}),
        ("ma_trend", {"trend_fast_period": 20, "trend_slow_period": 50, "ma_kind": "ema", "trend_max_adds": 0}),
    ],
}


def ensemble_member_specs(preset: str) -> list[tuple[str, dict[str, Any]]]:
    if preset not in ENSEMBLE_PRESETS:
        known = ", ".join(sorted(ENSEMBLE_PRESETS))
        raise ValueError(f"unknown ensemble_preset={preset!r}; choose one of: {known}")
    return [(strategy_id, dict(overrides)) for strategy_id, overrides in ENSEMBLE_PRESETS[preset]]


def _count(signals: Sequence[SignalAction], action: SignalAction) -> int:
    return sum(1 for signal in signals if signal == action)


class EnsembleAlgorithm(Algorithm):
    """Run several strategies on each bar and merge their signals.

    * **Entry** (flat): ``all`` = every child says ``buy``; ``majority`` = more than half;
      ``primary`` = first child says ``buy`` and no filter child says ``sell``.
    * **Exit** (in position): ``any`` = one ``sell``; ``all`` = every child ``sell``;
      ``primary`` = first child ``sell``.
    """

    name = "ensemble"

    def __init__(
        self,
        *,
        ensemble_preset: str = "1m_scalp_trend",
        ensemble_entry_rule: str = "all",
        ensemble_exit_rule: str = "any",
        member_factory: Callable[[str, dict[str, Any]], Algorithm] | None = None,
    ):
        if ensemble_entry_rule not in ENSEMBLE_ENTRY_RULES:
            raise ValueError(f"ensemble_entry_rule must be one of {ENSEMBLE_ENTRY_RULES}")
        if ensemble_exit_rule not in ENSEMBLE_EXIT_RULES:
            raise ValueError(f"ensemble_exit_rule must be one of {ENSEMBLE_EXIT_RULES}")
        self.ensemble_preset = ensemble_preset
        self.ensemble_entry_rule = ensemble_entry_rule
        self.ensemble_exit_rule = ensemble_exit_rule
        self._factory = member_factory or _default_member_factory
        specs = ensemble_member_specs(ensemble_preset)
        self._members: list[tuple[str, Algorithm]] = [
            (strategy_id, self._factory(strategy_id, **kwargs)) for strategy_id, kwargs in specs
        ]
        self._in_position = False
        self.last_child_signals: dict[str, SignalAction] = {}

    @property
    def child_ids(self) -> list[str]:
        return [strategy_id for strategy_id, _ in self._members]

    def reset(self) -> None:
        self._in_position = False
        self.last_child_signals = {}
        for _, child in self._members:
            child.reset()

    def sync_open_position(self, in_position: bool) -> None:
        self._in_position = in_position
        for _, child in self._members:
            child.sync_open_position(in_position)

    def _child_signals(self, bar: Bar) -> list[SignalAction]:
        signals: list[SignalAction] = []
        self.last_child_signals = {}
        for strategy_id, child in self._members:
            signal = child.on_bar(bar)
            signals.append(signal)
            self.last_child_signals[strategy_id] = signal
        return signals

    def _should_enter(self, signals: Sequence[SignalAction]) -> bool:
        if not signals:
            return False
        if self.ensemble_entry_rule == "all":
            return all(signal == "buy" for signal in signals)
        if self.ensemble_entry_rule == "majority":
            return _count(signals, "buy") > len(signals) / 2
        primary, *filters = signals
        if primary != "buy":
            return False
        return all(signal != "sell" for signal in filters)

    def _should_exit(self, signals: Sequence[SignalAction]) -> bool:
        if not signals:
            return False
        if self.ensemble_exit_rule == "all":
            return all(signal == "sell" for signal in signals)
        if self.ensemble_exit_rule == "any":
            return any(signal == "sell" for signal in signals)
        return signals[0] == "sell"

    def on_bar(self, bar: Bar) -> SignalAction:
        signals = self._child_signals(bar)
        if self._in_position:
            if self._should_exit(signals):
                self._in_position = False
                self.sync_open_position(False)
                return "sell"
            return "hold"
        if self._should_enter(signals):
            self._in_position = True
            self.sync_open_position(True)
            return "buy"
        return "hold"
