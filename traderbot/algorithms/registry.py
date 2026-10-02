from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from traderbot.algorithms.base import Algorithm
from traderbot.algorithms.strategies.bollinger import BollingerMeanReversionAlgorithm
from traderbot.algorithms.strategies.ema_cross import EmaCrossAlgorithm
from traderbot.algorithms.strategies.macd import MacdCrossAlgorithm
from traderbot.algorithms.strategies.rsi import RsiThresholdAlgorithm
from traderbot.algorithms.strategies.sma_cross import SmaCrossAlgorithm


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
        id="forecast_signal",
        name="ML forecast signal",
        summary="Use holdout forecast direction from LightGBM/Chronos (see traderbot ml run).",
        style="ml",
    ),
    StrategyCatalogEntry(
        id="breakout_atr",
        name="ATR breakout",
        summary="Enter on volatility expansion beyond recent range (planned).",
        style="breakout",
    ),
)

_IMPLEMENTED: dict[str, type[Algorithm]] = {
    "sma_cross": SmaCrossAlgorithm,
    "ema_cross": EmaCrossAlgorithm,
    "rsi_threshold": RsiThresholdAlgorithm,
    "macd_cross": MacdCrossAlgorithm,
    "bollinger_mean_reversion": BollingerMeanReversionAlgorithm,
}


def _price_context_kwargs(a: Any) -> dict[str, Any]:
    return {
        "context_bars": a.context_bars,
        "buy_min_recent_return": a.buy_min_recent_return,
        "sell_max_recent_return": a.sell_max_recent_return,
    }


_KWARGS_FROM_ARGS: dict[str, Callable[[Any], dict[str, Any]]] = {
    "sma_cross": lambda a: {"fast": a.fast, "slow": a.slow, "price_confirm": a.price_confirm},
    "ema_cross": lambda a: {"fast": a.fast, "slow": a.slow, "price_confirm": a.price_confirm},
    "rsi_threshold": lambda a: {
        "period": a.period,
        "oversold": a.oversold,
        "overbought": a.overbought,
        **_price_context_kwargs(a),
    },
    "macd_cross": lambda a: {
        "fast": a.fast,
        "slow": a.slow,
        "signal": a.signal,
        **_price_context_kwargs(a),
    },
    "bollinger_mean_reversion": lambda a: {
        "period": a.period,
        "num_std": a.num_std,
        **_price_context_kwargs(a),
    },
}


def list_strategies(*, implemented_only: bool = False) -> list[StrategyCatalogEntry]:
    if implemented_only:
        return [s for s in STRATEGY_CATALOG if s.implemented]
    return list(STRATEGY_CATALOG)


def implemented_strategy_ids() -> tuple[str, ...]:
    return tuple(_IMPLEMENTED.keys())


def algorithm_for_id(strategy_id: str, **kwargs: Any) -> Algorithm:
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
