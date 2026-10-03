from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from traderbot.algorithms.base import Algorithm
from traderbot.algorithms.strategies.bollinger import BollingerMeanReversionAlgorithm
from traderbot.algorithms.strategies.breakout_atr import BreakoutAtrAlgorithm
from traderbot.algorithms.strategies.chart_patterns import ChartPatternsAlgorithm
from traderbot.algorithms.strategies.ema_cross import EmaCrossAlgorithm
from traderbot.algorithms.strategies.forecast_signal import ForecastSignalAlgorithm
from traderbot.algorithms.strategies.macd import MacdCrossAlgorithm
from traderbot.algorithms.strategies.ml_gated import MlGatedAlgorithm
from traderbot.algorithms.strategies.rsi import RsiThresholdAlgorithm
from traderbot.algorithms.strategies.sma_cross import SmaCrossAlgorithm
from traderbot.algorithms.utils import price_context_kwargs_from_namespace

FORECAST_STRATEGY_IDS = frozenset({"forecast_signal", "ml_gated"})


@dataclass(frozen=True, slots=True)
class StrategyCatalogEntry:
    id: str
    name: str
    summary: str
    style: str
    implemented: bool = False


STRATEGY_CATALOG: tuple[StrategyCatalogEntry, ...] = (
    StrategyCatalogEntry(
        id="sma_cross",
        name="SMA crossover",
        summary="Long when fast simple moving average is above slow SMA; flat otherwise.",
        style="trend",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="ema_cross",
        name="EMA crossover",
        summary="Same as SMA cross but uses exponential moving averages (less lag).",
        style="trend",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="rsi_threshold",
        name="RSI thresholds",
        summary="Mean reversion: buy oversold, sell overbought (classic RSI bands).",
        style="mean_reversion",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="macd_cross",
        name="MACD signal cross",
        summary="Long when MACD line crosses above its signal line; flat on cross down.",
        style="trend",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="bollinger_mean_reversion",
        name="Bollinger mean reversion",
        summary="Buy at lower band, sell at upper band (rolling std envelope).",
        style="mean_reversion",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="chart_patterns",
        name="Chart patterns",
        summary="Double-bottom neckline break (buy) and double-top breakdown (sell), causal pivots.",
        style="pattern",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="breakout_atr",
        name="ATR breakout",
        summary="Enter on close breaking recent range by a multiple of ATR.",
        style="breakout",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="forecast_signal",
        name="ML forecast signal",
        summary="Long/short from holdout forecast log-returns (requires holdout_forecasts.json).",
        style="ml",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="ml_gated",
        name="ML-gated rule strategy",
        summary="Combine a rule strategy with holdout forecasts (forecast filters rule or the reverse).",
        style="ml",
        implemented=True,
    ),
)

_IMPLEMENTED: dict[str, type[Algorithm]] = {
    "sma_cross": SmaCrossAlgorithm,
    "ema_cross": EmaCrossAlgorithm,
    "rsi_threshold": RsiThresholdAlgorithm,
    "macd_cross": MacdCrossAlgorithm,
    "bollinger_mean_reversion": BollingerMeanReversionAlgorithm,
    "chart_patterns": ChartPatternsAlgorithm,
    "breakout_atr": BreakoutAtrAlgorithm,
    "forecast_signal": ForecastSignalAlgorithm,
    "ml_gated": MlGatedAlgorithm,
}


def _inner_kwargs_for_base(base_strategy_id: str, args: Any) -> dict[str, Any]:
    builder = _KWARGS_FROM_ARGS.get(base_strategy_id)
    if builder is None:
        return {}
    return builder(args)


_KWARGS_FROM_ARGS: dict[str, Callable[[Any], dict[str, Any]]] = {
    "sma_cross": lambda a: {"fast": a.fast, "slow": a.slow, "price_confirm": a.price_confirm},
    "ema_cross": lambda a: {"fast": a.fast, "slow": a.slow, "price_confirm": a.price_confirm},
    "rsi_threshold": lambda a: {
        "period": a.period,
        "oversold": a.oversold,
        "overbought": a.overbought,
        **price_context_kwargs_from_namespace(a),
    },
    "macd_cross": lambda a: {
        "fast": a.fast,
        "slow": a.slow,
        "signal": a.signal,
        **price_context_kwargs_from_namespace(a),
    },
    "bollinger_mean_reversion": lambda a: {
        "period": a.period,
        "num_std": a.num_std,
        **price_context_kwargs_from_namespace(a),
    },
    "chart_patterns": lambda a: {
        "swing_window_bars": a.swing_window_bars,
        "min_swing_separation_bars": a.min_swing_separation_bars,
        "low_tolerance_ratio": a.pattern_tolerance_ratio,
        "high_tolerance_ratio": a.pattern_tolerance_ratio,
        "pattern_score_threshold": a.pattern_score_threshold,
    },
    "breakout_atr": lambda a: {
        "lookback_bars": a.lookback_bars,
        "atr_period": a.atr_period,
        "atr_multiplier": a.atr_multiplier,
    },
    "forecast_signal": lambda a: {"forecast_threshold": a.forecast_threshold},
    "ml_gated": lambda a: {
        "base_strategy_id": a.ml_gated_base,
        "gate_mode": a.gate_mode,
        "forecast_threshold": a.forecast_threshold,
        **_inner_kwargs_for_base(a.ml_gated_base, a),
    },
}


def list_strategies(*, implemented_only = False) -> list[StrategyCatalogEntry]:
    if implemented_only:
        return [s for s in STRATEGY_CATALOG if s.implemented]
    return list(STRATEGY_CATALOG)


def implemented_strategy_ids() -> list[str]:
    return sorted(_IMPLEMENTED)


def backtest_strategy_ids(*, include_forecast_strategies: bool) -> list[str]:
    ids = implemented_strategy_ids()
    if include_forecast_strategies:
        return ids
    return [strategy_id for strategy_id in ids if strategy_id not in FORECAST_STRATEGY_IDS]


def algorithm_for_id(strategy_id: str, **kwargs: Any) -> Algorithm:
    if strategy_id == "ml_gated":
        forecast_by_timestamp = kwargs.pop("forecast_by_timestamp", {})
        base_strategy_id = kwargs.pop("base_strategy_id", "rsi_threshold")
        gate_mode = kwargs.pop("gate_mode", "forecast_filters_rule")
        forecast_threshold = float(kwargs.pop("forecast_threshold", 0.0))
        inner = algorithm_for_id(base_strategy_id, **kwargs)
        return MlGatedAlgorithm(
            inner=inner,
            forecast_by_timestamp=forecast_by_timestamp,
            gate_mode=gate_mode,
            forecast_threshold=forecast_threshold,
        )
    if strategy_id == "forecast_signal":
        forecast_by_timestamp = kwargs.pop("forecast_by_timestamp", {})
        forecast_threshold = float(kwargs.pop("forecast_threshold", 0.0))
        return ForecastSignalAlgorithm(
            forecast_by_timestamp=forecast_by_timestamp,
            forecast_threshold=forecast_threshold,
        )
    cls = _IMPLEMENTED.get(strategy_id)
    if cls is None:
        known = ", ".join(sorted(_IMPLEMENTED))
        raise ValueError(f"unsupported strategy_id={strategy_id!r}; implemented: {known}")
    return cls(**kwargs)


def strategy_kwargs_from_namespace(strategy_id: str, args: Any) -> dict[str, Any]:
    builder = _KWARGS_FROM_ARGS.get(strategy_id)
    if builder is None:
        return {}
    return builder(args)
