from __future__ import annotations

import argparse
from pathlib import Path


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
        "--forecast-json",
        type=Path,
        default=None,
        help="holdout_forecasts.json from traderbot ml run (required for forecast_signal / ml_gated)",
    )
    parser.add_argument(
        "--forecast-threshold",
        type=float,
        default=0.0,
        help="Min predicted log-return magnitude for ML forecast direction",
    )
    parser.add_argument(
        "--ml-gated-base",
        default="rsi_threshold",
        help="Rule strategy combined inside ml_gated",
    )
    parser.add_argument(
        "--gate-mode",
        choices=("forecast_filters_rule", "rule_filters_forecast"),
        default="forecast_filters_rule",
        help="How ml_gated combines rule signals with forecasts",
    )
