"""
Lightweight intraday backtest for minute bars (next-open execution, per-side fees).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class IntradayBacktestResult:
    equity_curve: pd.Series
    trades: int
    total_return: float
    sharpe: float
    max_drawdown: float
    bars: int
    resolution: str
    meta: dict[str, Any]
    window: dict[str, Any]


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def ema_cross_signals(close: pd.Series, fast: int = 12, slow: int = 48) -> pd.Series:
    """+1 long, 0 flat (signal known at bar close, traded next open)."""
    fast_ema = _ema(close, fast)
    slow_ema = _ema(close, slow)
    raw = (fast_ema > slow_ema).astype(int)
    return raw.shift(1).fillna(0).astype(int)


def run_intraday_backtest(
    ohlcv: pd.DataFrame,
    *,
    resolution: str,
    fast_ema: int = 12,
    slow_ema: int = 48,
    fee_per_side: float = 0.00045,
    initial_capital: float = 10_000.0,
) -> IntradayBacktestResult:
    if ohlcv.empty or len(ohlcv) < slow_ema + 5:
        raise ValueError("not enough bars for intraday backtest")

    close = ohlcv["close"].astype(float)
    open_ = ohlcv["open"].astype(float)
    position = ema_cross_signals(close, fast=fast_ema, slow=slow_ema)

    equity = initial_capital
    equities: list[float] = []
    trades = 0
    prev_pos = 0

    # Position at bar i is known from prior close; PnL is open[i] -> open[i+1] while holding pos[i].
    for i in range(len(ohlcv) - 1):
        pos = int(position.iloc[i])
        ret = (open_.iloc[i + 1] / open_.iloc[i] - 1.0) * pos
        equity *= 1.0 + ret
        if pos != prev_pos:
            trades += 1
            equity *= (1.0 - fee_per_side) ** 2 if pos != 0 and prev_pos != 0 else (1.0 - fee_per_side)
        prev_pos = pos
        equities.append(equity)
    equities.append(equity)

    equity_curve = pd.Series(equities, index=ohlcv.index, name="equity")
    rets = equity_curve.pct_change().dropna()
    vol_bar = float(rets.std(ddof=0)) if len(rets) else 0.0
    sharpe = float(rets.mean() / vol_bar) if vol_bar > 0 else 0.0
    peak = equity_curve.cummax()
    dd = (equity_curve / peak - 1.0).min()

    from traderbot.finrl.window_metrics import equity_window_metrics

    window = equity_window_metrics(equity_curve / initial_capital)

    return IntradayBacktestResult(
        equity_curve=equity_curve,
        trades=trades,
        total_return=float(equity_curve.iloc[-1] / initial_capital - 1.0),
        sharpe=sharpe,
        max_drawdown=float(dd),
        bars=len(ohlcv),
        resolution=str(resolution),
        meta={"fast_ema": fast_ema, "slow_ema": slow_ema, "fee_per_side": fee_per_side},
        window=window,
    )
