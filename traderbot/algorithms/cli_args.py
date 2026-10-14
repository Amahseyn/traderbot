from __future__ import annotations

import argparse
from typing import Any


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
        "hedge_csv": None,
        "lookback": 60,
        "hedge_lookback": 60,
        "entry_z": 2.0,
        "exit_z": 0.5,
        "use_dynamic_hedge_ratio": True,
        "fixed_hedge_ratio": 1.0,
        "grid_low_pct": -0.08,
        "grid_high_pct": 0.04,
        "grid_levels": 5,
        "take_profit_pct": 0.01,
    }
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
    parser.add_argument(
        "--hedge-csv",
        default=None,
        help="Second OHLC CSV for pair_trading (aligned by timestamp on primary bars)",
    )
    parser.add_argument("--lookback", type=int, default=60, help="Pair trading z-score lookback")
    parser.add_argument("--hedge-lookback", type=int, default=60, help="Rolling hedge ratio window")
    parser.add_argument("--entry-z", type=float, default=2.0, help="Enter long when z-score below -entry_z")
    parser.add_argument("--exit-z", type=float, default=0.5, help="Exit when z-score above -exit_z")
    parser.add_argument(
        "--use-dynamic-hedge-ratio",
        action="store_true",
        default=True,
        help="Estimate hedge ratio with rolling OLS on log prices",
    )
    parser.add_argument(
        "--no-dynamic-hedge-ratio",
        action="store_false",
        dest="use_dynamic_hedge_ratio",
        help="Use fixed hedge ratio for pair trading",
    )
    parser.add_argument("--fixed-hedge-ratio", type=float, default=1.0, help="Fixed hedge ratio when dynamic is off")
    parser.add_argument("--grid-low-pct", type=float, default=-0.08, help="Grid lower bound vs anchor (fraction)")
    parser.add_argument("--grid-high-pct", type=float, default=0.04, help="Grid upper bound vs anchor (fraction)")
    parser.add_argument("--grid-levels", type=int, default=5, help="Number of grid buy levels")
    parser.add_argument("--take-profit-pct", type=float, default=0.01, help="Grid take-profit fraction from entry")
