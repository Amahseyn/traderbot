from __future__ import annotations

import argparse


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
