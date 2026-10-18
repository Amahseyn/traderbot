from __future__ import annotations

import argparse
from typing import Any


# (name, type, default, help) for strategies added after the original flag set.
EXTRA_STRATEGY_PARAMS: tuple[tuple[str, type, object, str], ...] = (
    ("trend_fast_period", int, 50, "ma_trend fast moving average period"),
    ("trend_slow_period", int, 200, "ma_trend slow moving average period"),
    ("ma_kind", str, "sma", "ma_trend average type: sma or ema"),
    ("ma_entry_mode", str, "golden_cross", "ma_trend entry: golden_cross or price_cross"),
    ("trailing_stop_pct", float, 0.0, "Trailing stop below the peak close (0=off; ma_trend, rsi_divergence, momentum_shock)"),
    ("trend_max_adds", int, 0, "ma_trend tranches added on retracements to the fast MA"),
    ("rsi_trend_entry", float, 55.0, "rsi_trend: buy when RSI crosses up through this level"),
    ("rsi_trend_exit", float, 45.0, "rsi_trend: sell when RSI crosses down through this level"),
    ("trend_filter_period", int, 50, "rsi_trend EMA trend filter period"),
    ("divergence_rsi_level", float, 40.0, "rsi_divergence: prior swing-low RSI must be at or below this"),
    ("divergence_confirm_bars", int, 5, "rsi_divergence: bars allowed for the confirmation close"),
    ("divergence_stop_buffer_pct", float, 0.005, "rsi_divergence stop buffer below the swing low"),
    ("range_max_width_pct", float, 0.06, "range_breakout: max (high-low)/mean close for a consolidation"),
    ("breakout_volume_multiplier", float, 1.5, "range_breakout: breakout volume vs range average"),
    ("breakout_stop_fraction", float, 0.5, "range_breakout: stop at range high minus this fraction of height"),
    ("measured_move_multiplier", float, 1.0, "range_breakout target = range high + height * this"),
    ("dip_lookback_bars", int, 10, "scalp_dip: bars for the recent high"),
    ("dip_pct", float, 0.004, "scalp_dip: dip below the recent high that triggers a buy"),
    ("take_profit_pct", float, 0.0075, "scalp_dip take profit"),
    ("stop_loss_pct", float, 0.005, "scalp_dip stop loss"),
    ("session_end_hour_utc", int, -1, "scalp_dip: go flat during this UTC hour (-1=off)"),
    ("cooldown_bars_after_loss", int, 3, "scalp_dip: bars to wait after a losing trade"),
    ("scalp_position_fraction", float, 1.0, "scalp_dip fixed position size (fraction of equity)"),
    ("dca_interval_bars", int, 24, "dca: bars between purchases"),
    ("dca_order_count", int, 10, "dca: number of equal purchases (each = initial cash / count)"),
    ("grid_range_pct", float, 0.05, "grid: range half-width around the anchor mean close"),
    ("grid_levels", int, 5, "grid: number of bands"),
    ("grid_breakout_pct", float, 0.01, "grid: shut down when close exits the range by this much"),
    ("grid_reanchor_bars", int, 0, "grid: re-anchor this many bars after a shutdown (0=never)"),
    ("shock_return_std", float, 2.5, "momentum_shock: bar return z-score that counts as an event"),
    ("shock_volume_multiplier", float, 2.0, "momentum_shock: event volume vs average"),
    ("shock_hold_bars", int, 12, "momentum_shock: max bars to hold after an event"),
    ("ml_horizon_bars", int, 6, "online_logistic: label horizon (bars ahead)"),
    ("ml_learning_rate", float, 0.05, "online_logistic SGD learning rate"),
    ("ml_buy_threshold", float, 0.55, "online_logistic: buy when P(up) is at least this"),
    ("ml_sell_threshold", float, 0.45, "online_logistic: sell when P(up) is at most this"),
    ("ml_warmup_samples", int, 100, "online_logistic: labelled samples before trading"),
    (
        "ensemble_preset",
        str,
        "1m_scalp_trend",
        "ensemble: preset member set (1m_scalp_trend, 1m_pattern_ma, 1m_ml_trend, intraday_trend_stack)",
    ),
    ("ensemble_entry_rule", str, "all", "ensemble entry: all, majority, or primary"),
    ("ensemble_exit_rule", str, "any", "ensemble exit: any, all, or primary"),
    ("ensemble_filter_mode", str, "signal", "ensemble: 'signal' (members vote) or 'state' (non-primary members gate entries by trend state)"),
    ("scalp_preset", str, "", "scalp_dip preset (1m or 5m); explicit flags still win"),
    ("scalp_threshold_mode", str, "fixed", "scalp_dip thresholds: fixed (pct) or atr (x ATR)"),
    ("dip_atr_mult", float, 1.5, "scalp_dip atr mode: dip size in ATRs"),
    ("tp_atr_mult", float, 2.0, "scalp_dip atr mode: take profit in ATRs"),
    ("sl_atr_mult", float, 1.5, "scalp_dip atr mode: stop loss in ATRs"),
    ("scalp_order_mode", str, "legacy", "scalp_dip execution: legacy, bracket (market + TP/stop), maker (post-only entry + TP/stop)"),
    ("entry_offset_pct", float, 0.0002, "scalp_dip maker mode: limit entry offset from the signal close"),
    ("entry_ttl_bars", int, 2, "scalp_dip maker mode: bars a limit entry rests before cancel"),
    ("min_volume_ratio", float, 0.0, "scalp_dip: min bar volume vs lookback mean (0=off)"),
    ("max_spread_pct", float, 0.0, "scalp_dip: max bid/ask spread when the bar carries spread_pct (0=off)"),
    ("allow_short", int, 0, "1 = allow shorts (Hyperliquid perps only; spot/Nobitex stay long-only)"),
    ("mm_vol_spread_mult", float, 0.5, "perp_market_making: half-spread floor as a multiple of ATR%"),
    ("mm_adverse_move_atr", float, 2.0, "perp_market_making: skip entries after a bar move > this many ATRs (0=off)"),
    ("mm_trend_ema_period", int, 20, "perp_market_making: EMA for the trend guard"),
    ("mm_trend_guard", int, 1, "perp_market_making: 1 = no bids while the EMA falls (asks while it rises)"),
    ("mm_stop_loss_pct", float, 0.004, "perp_market_making protective stop from the fill (0=off)"),
    ("mm_min_profit_pct", float, 0.0004, "perp_market_making: exit quote at least this far beyond entry"),
    ("mm_order_fraction", float, 1.0, "perp_market_making: position size as a fraction of equity"),
)


def default_strategy_namespace(**overrides: Any) -> argparse.Namespace:
    """Defaults aligned with ``add_strategy_param_flags`` for Lab jobs and compare sessions."""
    values: dict[str, Any] = {
        "fast": 5,
        "slow": 20,
        "signal": 9,
        "period": 14,
        "oversold": 30.0,
        "overbought": 70.0,
        "num_std": 2.0,
        "context_bars": 0,
        "buy_min_recent_return": -0.03,
        "sell_max_recent_return": 0.03,
        "price_confirm": False,
        "buy_min_fine_last_5m": None,
        "sell_max_fine_last_5m": None,
        "lookback_bars": 20,
        "atr_period": 14,
        "atr_multiplier": 1.5,
        "swing_window_bars": 3,
        "min_swing_separation_bars": 4,
        "pattern_tolerance_ratio": 0.02,
        "pattern_score_threshold": 0.35,
        "no_auto_fine": False,
        "fine_csv": None,
        "grid_start_price": 90.0,
        "grid_end_price": 110.0,
        "grid_count": 5,
        "grid_take_profit_pct": 0.01,
        "pair_lookback_period": 30,
        "pair_entry_threshold": 2.0,
        "pair_exit_threshold": 0.5,
        "pair_hedge_ratio": 1.0,
        "mm_half_spread_pct": 0.0005,
        "mm_inventory_skew": 0.0,
    }
    values.update({name: default for name, _kind, default, _help in EXTRA_STRATEGY_PARAMS})
    values.update(overrides)
    return argparse.Namespace(**values)


def merge_strategy_namespace(args: Any | None) -> argparse.Namespace:
    """Fill missing strategy params so Lab jobs and partial Namespace objects work for every strategy."""
    defaults = default_strategy_namespace()
    if args is None:
        return defaults
    merged = vars(defaults)
    merged.update(vars(args))
    return argparse.Namespace(**merged)


def add_strategy_param_flags(parser: argparse.ArgumentParser) -> None:
    """Strategy hyperparameters shared by strategy, backtest, and terminal CLIs."""
    parser.add_argument("--fast", type=int, default=5, help="SMA/EMA/MACD fast period")
    parser.add_argument("--slow", type=int, default=20, help="SMA/EMA/MACD slow period")
    parser.add_argument("--signal", type=int, default=9, help="MACD signal period")
    parser.add_argument("--period", type=int, default=14, help="RSI or Bollinger lookback")
    parser.add_argument("--oversold", type=float, default=30.0, help="RSI oversold threshold")
    parser.add_argument("--overbought", type=float, default=70.0, help="RSI overbought threshold")
    parser.add_argument("--num-std", type=float, default=2.0, help="Bollinger band width (std devs)")
    parser.add_argument(
        "--context-bars",
        type=int,
        default=0,
        help="Recent-price filter lookback (0=off). Mean-reversion / MACD: block entries against sharp recent moves.",
    )
    parser.add_argument(
        "--buy-min-recent-return",
        type=float,
        default=-0.03,
        help="With --context-bars>0, skip buys if cumulative return over lookback is below this (e.g. -0.03).",
    )
    parser.add_argument(
        "--sell-max-recent-return",
        type=float,
        default=0.03,
        help="With --context-bars>0, skip sells if cumulative return over lookback is above this.",
    )
    parser.add_argument(
        "--price-confirm",
        action="store_true",
        help="SMA/EMA: require close on the trend side of the fast average before entering.",
    )
    parser.add_argument(
        "--buy-min-fine-last-5m",
        type=float,
        default=None,
        help="With 1m-enriched bars, skip buys if fine_return_last_5m is below this.",
    )
    parser.add_argument(
        "--sell-max-fine-last-5m",
        type=float,
        default=None,
        help="With 1m-enriched bars, skip sells if fine_return_last_5m is above this.",
    )
    parser.add_argument("--lookback-bars", type=int, default=20, help="ATR breakout range lookback")
    parser.add_argument("--atr-period", type=int, default=14, help="ATR period for breakout_atr")
    parser.add_argument("--atr-multiplier", type=float, default=1.5, help="ATR breakout buffer multiplier")
    parser.add_argument("--swing-window-bars", type=int, default=3, help="Chart pattern pivot window")
    parser.add_argument(
        "--min-swing-separation-bars",
        type=int,
        default=4,
        help="Minimum bars between pattern pivots",
    )
    parser.add_argument(
        "--pattern-tolerance-ratio",
        type=float,
        default=0.02,
        help="Relative tolerance for matching double top/bottom pivots",
    )
    parser.add_argument(
        "--pattern-score-threshold",
        type=float,
        default=0.35,
        help="Minimum pattern score before chart_patterns emits buy/sell",
    )
    for name, kind, default, help_text in EXTRA_STRATEGY_PARAMS:
        parser.add_argument(f"--{name.replace('_', '-')}", type=kind, default=default, help=help_text)
