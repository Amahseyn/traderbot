from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from traderbot.algorithms.base import Algorithm
from traderbot.algorithms.strategies.bollinger import BollingerMeanReversionAlgorithm
from traderbot.algorithms.strategies.breakout_atr import BreakoutAtrAlgorithm
from traderbot.algorithms.strategies.chart_patterns import ChartPatternsAlgorithm
from traderbot.algorithms.strategies.ema_cross import EmaCrossAlgorithm
from traderbot.algorithms.strategies.macd import MacdCrossAlgorithm
from traderbot.algorithms.strategies.rsi import RsiThresholdAlgorithm
from traderbot.algorithms.strategies.grid_trading import GridTradingAlgorithm
from traderbot.algorithms.strategies.pair_trading import PairTradingSpreadAlgorithm
from traderbot.algorithms.strategies.sma_cross import SmaCrossAlgorithm
from traderbot.algorithms.utils import price_context_kwargs_from_namespace

STRATEGY_MODE_RULES = "strategies"


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
        id="pair_trading",
        name="Pair trading (spread z-score)",
        summary="Mean-revert log spread vs a hedge pair (e.g. ETH vs BTC on Nobitex). Requires hedge CSV.",
        style="stat_arb",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="grid_trading",
        name="Grid trading",
        summary="Range grid dip buys with take-profit exits (Hummingbot grid_strike inspired).",
        style="grid",
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
    "pair_trading": PairTradingSpreadAlgorithm,
    "grid_trading": GridTradingAlgorithm,
}

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
    "pair_trading": lambda a: {
        "lookback": a.lookback,
        "hedge_lookback": a.hedge_lookback,
        "entry_z": a.entry_z,
        "exit_z": a.exit_z,
        "use_dynamic_hedge_ratio": a.use_dynamic_hedge_ratio,
        "fixed_hedge_ratio": a.fixed_hedge_ratio,
    },
    "grid_trading": lambda a: {
        "grid_low_pct": a.grid_low_pct,
        "grid_high_pct": a.grid_high_pct,
        "grid_levels": a.grid_levels,
        "take_profit_pct": a.take_profit_pct,
    },
}


def list_strategies(*, implemented_only = False) -> list[StrategyCatalogEntry]:
    if implemented_only:
        return [s for s in STRATEGY_CATALOG if s.implemented]
    return list(STRATEGY_CATALOG)


def implemented_strategy_ids() -> list[str]:
    return sorted(_IMPLEMENTED)


def backtest_strategy_ids() -> list[str]:
    return implemented_strategy_ids()


def normalize_strategy_mode(mode: str | None) -> str:
    if mode is None or str(mode).strip() == "":
        return STRATEGY_MODE_RULES
    value = str(mode).strip().lower()
    if value != STRATEGY_MODE_RULES:
        raise ValueError("mode must be 'strategies'")
    return value


def strategy_ids_for_mode(mode: str | None) -> list[str]:
    normalize_strategy_mode(mode)
    return backtest_strategy_ids()


def algorithm_for_id(strategy_id: str, **kwargs: Any) -> Algorithm:
    cls = _IMPLEMENTED.get(strategy_id)
    if cls is None:
        known = ", ".join(sorted(_IMPLEMENTED))
        raise ValueError(f"unsupported strategy_id={strategy_id!r}; implemented: {known}")
    return cls(**kwargs)


def strategy_kwargs_from_namespace(strategy_id: str, namespace: Any) -> dict[str, Any]:
    builder = _KWARGS_FROM_ARGS.get(strategy_id)
    if builder is None:
        return {}
    return builder(namespace)


_ALGO_KWARG_TO_NAMESPACE_FIELD = {
    "low_tolerance_ratio": "pattern_tolerance_ratio",
    "high_tolerance_ratio": "pattern_tolerance_ratio",
}


def strategy_param_names(strategy_id: str) -> list[str]:
    """Namespace field names this strategy actually consumes (sweepable knobs)."""
    if strategy_id not in _IMPLEMENTED:
        known = ", ".join(sorted(_IMPLEMENTED))
        raise ValueError(f"unsupported strategy_id={strategy_id!r}; implemented: {known}")
    from traderbot.algorithms.cli_args import default_strategy_namespace

    kwargs = strategy_kwargs_from_namespace(strategy_id, default_strategy_namespace())
    names = [_ALGO_KWARG_TO_NAMESPACE_FIELD.get(key, key) for key in kwargs]
    return list(dict.fromkeys(names))
