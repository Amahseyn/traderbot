from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from traderbot.algorithms.base import Algorithm
from traderbot.algorithms.strategies.bollinger import BollingerMeanReversionAlgorithm
from traderbot.algorithms.strategies.breakout_atr import BreakoutAtrAlgorithm
from traderbot.algorithms.strategies.pair_trading import PairTradingAlgorithm
from traderbot.algorithms.strategies.perp_market_making import PerpMarketMakingAlgorithm
from traderbot.algorithms.strategies.spot_grid import SpotGridAlgorithm
from traderbot.algorithms.strategies.chart_patterns import ChartPatternsAlgorithm
from traderbot.algorithms.strategies.dca import DcaAlgorithm
from traderbot.algorithms.strategies.grid import GridAlgorithm
from traderbot.algorithms.strategies.ma_trend import MaTrendAlgorithm
from traderbot.algorithms.strategies.momentum_shock import MomentumShockAlgorithm
from traderbot.algorithms.strategies.online_logistic import OnlineLogisticAlgorithm
from traderbot.algorithms.strategies.range_breakout import RangeBreakoutAlgorithm
from traderbot.algorithms.strategies.rsi_divergence import RsiDivergenceAlgorithm
from traderbot.algorithms.strategies.rsi_trend import RsiTrendAlgorithm
from traderbot.algorithms.strategies.scalp_dip import ScalpDipAlgorithm
from traderbot.algorithms.strategies.ensemble import EnsembleAlgorithm
from traderbot.algorithms.strategies.ema_cross import EmaCrossAlgorithm
from traderbot.algorithms.strategies.finrl_ema_intraday import FinrlEmaIntradayAlgorithm
from traderbot.algorithms.strategies.macd import MacdCrossAlgorithm
from traderbot.algorithms.strategies.rsi import RsiThresholdAlgorithm
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
        id="spot_grid",
        name="Spot grid",
        summary="Long-only grid on OHLC; Nobitex spot or Hyperliquid perp candles (paper).",
        style="grid",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="pair_trading",
        name="Pair trading (stat arb)",
        summary="Spread z-score mean reversion; Nobitex spot rebalance or Hyperliquid perp long/short legs.",
        style="pair",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="funding_carry",
        name="Funding carry",
        summary="Short perp when funding is elevated to collect payments (Hyperliquid only).",
        style="carry",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="perp_market_making",
        name="Perp market making",
        summary="Post-only bid/ask quoted from the prior bar; fills only on trade-through at the maker fee; inventory skew, adverse-move/trend guard, protective stop.",
        style="market_making",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="ma_trend",
        name="MA trend (golden cross)",
        summary="50/200-style golden cross or price-over-MA entry; exit below slow MA / death cross; retracement adds; trailing stop.",
        style="trend",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="rsi_trend",
        name="RSI trend",
        summary="Momentum: buy RSI crossing up through 55 above an EMA filter; exit RSI below 45 or filter lost.",
        style="trend",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="rsi_divergence",
        name="RSI divergence swing",
        summary="Bullish divergence at confirmed swing lows with confirmation close; stop under the swing low; trailing stop; bearish divergence exit.",
        style="swing",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="range_breakout",
        name="Range breakout",
        summary="Consolidation range breakout on volume; stop just below the breakout; measured-move target.",
        style="breakout",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="scalp_dip",
        name="Micro-dip scalper",
        summary="Low-timeframe dip buys with bounce confirmation; fixed or ATR-scaled TP/SL, optional maker entry + brackets, volume/spread filters, 1m/5m presets.",
        style="scalping",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="dca",
        name="Dollar-cost averaging",
        summary="Fixed cash amount every N bars; summary includes a lump-sum comparison.",
        style="accumulation",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="grid",
        name="Grid trading",
        summary="Range grid: more inventory near the bottom, less near the top; shuts down on range breakout.",
        style="range",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="momentum_shock",
        name="Event momentum (shock proxy)",
        summary="PROXY for news/event momentum: buys price+volume shocks. No news feed; pluggable event source.",
        style="event",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="online_logistic",
        name="Online logistic signal",
        summary="Walk-forward logistic regression on returns/volatility/RSI/momentum/volume (idea from CloddsBot, MIT).",
        style="ml",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="ensemble",
        name="Strategy ensemble",
        summary="Combine preset child strategies (e.g. 1m scalp + RSI trend); entry all/majority/primary, exit any/all/primary.",
        style="meta",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="finrl_ema_intraday",
        name="FinRL EMA intraday",
        summary="FinRL-Trading Hyperliquid preset: EMA 12/48 on 1m/5m bars (pairs with FinRL intraday pipeline).",
        style="trend",
        implemented=True,
    ),
    StrategyCatalogEntry(
        id="finrl_adaptive_rotation",
        name="FinRL adaptive rotation (equity)",
        summary="Multi-asset US equity rotation from FinRL-Trading; run via finrl platform pipeline (not single-CSV backtest).",
        style="portfolio",
        implemented=False,
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
    "spot_grid": SpotGridAlgorithm,
    "perp_market_making": PerpMarketMakingAlgorithm,
    "ma_trend": MaTrendAlgorithm,
    "rsi_trend": RsiTrendAlgorithm,
    "rsi_divergence": RsiDivergenceAlgorithm,
    "range_breakout": RangeBreakoutAlgorithm,
    "scalp_dip": ScalpDipAlgorithm,
    "dca": DcaAlgorithm,
    "grid": GridAlgorithm,
    "momentum_shock": MomentumShockAlgorithm,
    "online_logistic": OnlineLogisticAlgorithm,
    "ensemble": EnsembleAlgorithm,
    "finrl_ema_intraday": FinrlEmaIntradayAlgorithm,
}


def _pick(*names: str) -> Callable[[Any], dict[str, Any]]:
    return lambda namespace: {name: getattr(namespace, name) for name in names}


_SCALP_DIP_FIELDS = (
    "dip_lookback_bars",
    "dip_pct",
    "take_profit_pct",
    "stop_loss_pct",
    "session_end_hour_utc",
    "cooldown_bars_after_loss",
    "scalp_position_fraction",
    "scalp_threshold_mode",
    "dip_atr_mult",
    "tp_atr_mult",
    "sl_atr_mult",
    "atr_period",
    "scalp_order_mode",
    "entry_offset_pct",
    "entry_ttl_bars",
    "min_volume_ratio",
    "max_spread_pct",
)


def _scalp_dip_kwargs(namespace: Any) -> dict[str, Any]:
    """scalp_dip kwargs; a ``scalp_preset`` fills fields still at their CLI default."""
    from traderbot.algorithms.cli_args import default_strategy_namespace
    from traderbot.algorithms.strategies.scalp_dip import SCALP_DIP_PRESETS

    kwargs = {name: getattr(namespace, name) for name in _SCALP_DIP_FIELDS if hasattr(namespace, name)}
    kwargs["allow_short"] = bool(getattr(namespace, "allow_short", 0))
    preset_name = str(getattr(namespace, "scalp_preset", "") or "").strip()
    if preset_name:
        if preset_name not in SCALP_DIP_PRESETS:
            raise ValueError(f"unknown scalp_preset {preset_name!r}; choose from {sorted(SCALP_DIP_PRESETS)}")
        defaults = default_strategy_namespace()
        for name, value in SCALP_DIP_PRESETS[preset_name].items():
            if kwargs.get(name) == getattr(defaults, name, None):
                kwargs[name] = value
    return kwargs


_KWARGS_FROM_ARGS: dict[str, Callable[[Any], dict[str, Any]]] = {
    "sma_cross": lambda a: {"fast": a.fast, "slow": a.slow, "price_confirm": a.price_confirm},
    "ema_cross": lambda a: {"fast": a.fast, "slow": a.slow, "price_confirm": a.price_confirm},
    "finrl_ema_intraday": lambda a: {
        "fast": a.fast,
        "slow": a.slow,
        "price_confirm": a.price_confirm,
        "signal_style": getattr(a, "signal_style", "level_lag"),
    },
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
    "spot_grid": lambda a: {
        "start_price": a.grid_start_price,
        "end_price": a.grid_end_price,
        "grid_count": a.grid_count,
        "take_profit_pct": a.grid_take_profit_pct,
    },
    "perp_market_making": lambda a: {
        "half_spread_pct": a.mm_half_spread_pct,
        "inventory_skew": a.mm_inventory_skew,
        "vol_spread_mult": a.mm_vol_spread_mult,
        "atr_period": a.atr_period,
        "adverse_move_atr": a.mm_adverse_move_atr,
        "trend_ema_period": a.mm_trend_ema_period,
        "trend_guard": bool(a.mm_trend_guard),
        "stop_loss_pct": a.mm_stop_loss_pct,
        "min_profit_pct": a.mm_min_profit_pct,
        "order_fraction": a.mm_order_fraction,
        "allow_short": bool(a.allow_short),
    },
    "ma_trend": _pick(
        "trend_fast_period", "trend_slow_period", "ma_kind", "ma_entry_mode", "trailing_stop_pct", "trend_max_adds"
    ),
    "rsi_trend": _pick("period", "rsi_trend_entry", "rsi_trend_exit", "trend_filter_period"),
    "rsi_divergence": _pick(
        "period",
        "swing_window_bars",
        "divergence_rsi_level",
        "divergence_confirm_bars",
        "divergence_stop_buffer_pct",
        "trailing_stop_pct",
    ),
    "range_breakout": _pick(
        "lookback_bars",
        "range_max_width_pct",
        "breakout_volume_multiplier",
        "breakout_stop_fraction",
        "measured_move_multiplier",
    ),
    "scalp_dip": lambda a: _scalp_dip_kwargs(a),
    "dca": _pick("dca_interval_bars", "dca_order_count"),
    "grid": _pick("lookback_bars", "grid_range_pct", "grid_levels", "grid_breakout_pct", "grid_reanchor_bars"),
    "momentum_shock": _pick(
        "lookback_bars", "shock_return_std", "shock_volume_multiplier", "shock_hold_bars", "trailing_stop_pct"
    ),
    "online_logistic": _pick(
        "period",
        "lookback_bars",
        "ml_horizon_bars",
        "ml_learning_rate",
        "ml_buy_threshold",
        "ml_sell_threshold",
        "ml_warmup_samples",
    ),
    "ensemble": _pick("ensemble_preset", "ensemble_entry_rule", "ensemble_exit_rule"),
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


def build_strategy_kwargs_for_bars(
    strategy_id: str,
    bars: list[dict[str, Any]],
    *,
    csv_path: str | Path | None = None,
    base_namespace: Any | None = None,
) -> dict[str, Any]:
    """Namespace kwargs for ``algorithm_for_id`` using bar-derived defaults (e.g. spot grid bounds)."""
    from traderbot.algorithms.strategy_defaults import namespace_for_strategy_backtest
    from traderbot.algorithms.strategies.spot_grid import grid_price_bounds_from_bars

    namespace = namespace_for_strategy_backtest(
        strategy_id,
        base_namespace,
        csv_path=Path(csv_path) if csv_path is not None else None,
    )
    if strategy_id == "spot_grid" and bars:
        low, high = grid_price_bounds_from_bars(bars)
        namespace.grid_start_price = low
        namespace.grid_end_price = high
    return strategy_kwargs_from_namespace(strategy_id, namespace)


def algorithm_for_id(strategy_id: str, **kwargs: Any) -> Algorithm:
    if strategy_id == "pair_trading":
        raise ValueError(
            "pair_trading requires two series; use pair_algorithm_for_id() and "
            "run_pair_backtest_for_exchange() instead of run_backtest().",
        )
    if strategy_id == "funding_carry":
        raise ValueError(
            "funding_carry requires Hyperliquid funding history; use run_funding_carry_backtest().",
        )
    cls = _IMPLEMENTED.get(strategy_id)
    if cls is None:
        known = ", ".join(sorted(_IMPLEMENTED) + ["pair_trading", "funding_carry"])
        raise ValueError(f"unsupported strategy_id={strategy_id!r}; implemented: {known}")
    return cls(**kwargs)


def pair_algorithm_for_id(strategy_id: str, **kwargs: Any) -> PairTradingAlgorithm:
    if strategy_id != "pair_trading":
        raise ValueError(f"pair_algorithm_for_id only supports pair_trading, got {strategy_id!r}")
    return PairTradingAlgorithm(**kwargs)


def strategy_kwargs_from_namespace(strategy_id: str, namespace: Any) -> dict[str, Any]:
    builder = _KWARGS_FROM_ARGS.get(strategy_id)
    if builder is None:
        return {}
    return builder(namespace)


_ALGO_KWARG_TO_NAMESPACE_FIELD = {
    "low_tolerance_ratio": "pattern_tolerance_ratio",
    "high_tolerance_ratio": "pattern_tolerance_ratio",
}

_STRATEGY_KWARG_NAMESPACE: dict[str, dict[str, str]] = {
    "spot_grid": {
        "start_price": "grid_start_price",
        "end_price": "grid_end_price",
        "take_profit_pct": "grid_take_profit_pct",
    },
    "perp_market_making": {
        "half_spread_pct": "mm_half_spread_pct",
        "inventory_skew": "mm_inventory_skew",
        "vol_spread_mult": "mm_vol_spread_mult",
        "adverse_move_atr": "mm_adverse_move_atr",
        "trend_ema_period": "mm_trend_ema_period",
        "trend_guard": "mm_trend_guard",
        "stop_loss_pct": "mm_stop_loss_pct",
        "min_profit_pct": "mm_min_profit_pct",
        "order_fraction": "mm_order_fraction",
    },
}


def _namespace_field_for_kwarg(strategy_id: str, kwarg: str) -> str:
    override = _STRATEGY_KWARG_NAMESPACE.get(strategy_id, {}).get(kwarg)
    if override is not None:
        return override
    return _ALGO_KWARG_TO_NAMESPACE_FIELD.get(kwarg, kwarg)


def strategy_param_defaults(strategy_id: str) -> dict[str, Any]:
    """Default knob values per namespace field name (includes kwargs not on CLI namespace)."""
    from traderbot.algorithms.cli_args import default_strategy_namespace

    namespace = default_strategy_namespace()
    return {
        _namespace_field_for_kwarg(strategy_id, key): value
        for key, value in strategy_kwargs_from_namespace(strategy_id, namespace).items()
    }


def strategy_param_names(strategy_id: str) -> list[str]:
    """Namespace field names this strategy actually consumes (sweepable knobs)."""
    if strategy_id not in _IMPLEMENTED:
        known = ", ".join(sorted(_IMPLEMENTED))
        raise ValueError(f"unsupported strategy_id={strategy_id!r}; implemented: {known}")
    from traderbot.algorithms.cli_args import default_strategy_namespace

    kwargs = strategy_kwargs_from_namespace(strategy_id, default_strategy_namespace())
    names = [_namespace_field_for_kwarg(strategy_id, key) for key in kwargs]
    return list(dict.fromkeys(names))
