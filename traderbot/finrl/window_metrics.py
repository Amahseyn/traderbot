"""Performance metrics over a fixed number of bars (no annualization)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def equity_window_metrics(equity: pd.Series, n_bars: int | None = None) -> dict:
    """
    Metrics on the last ``n_bars`` points of an equity curve (level index, starts ~1.0).
    """
    eq = equity.dropna().astype(float)
    if n_bars is not None and len(eq) > n_bars:
        eq = eq.iloc[-n_bars:]
    rets = eq.pct_change().dropna()
    n = len(rets)
    if n < 1:
        return {"n_bars": len(eq), "n_returns": 0}

    total_return = float(eq.iloc[-1] / eq.iloc[0] - 1.0)
    mean_bar = float(rets.mean())
    vol_bar = float(rets.std(ddof=0))
    sharpe_per_bar = float(mean_bar / vol_bar) if vol_bar > 0 else 0.0
    peak = eq.cummax()
    max_dd = float((eq / peak - 1.0).min())
    win_rate = float((rets > 0).sum() / n)

    return {
        "n_bars": int(len(eq)),
        "n_returns": int(n),
        "total_return_pct": round(total_return * 100, 4),
        "mean_return_per_bar_pct": round(mean_bar * 100, 6),
        "volatility_per_bar_pct": round(vol_bar * 100, 6),
        "sharpe_per_bar": round(sharpe_per_bar, 4),
        "max_drawdown_pct": round(max_dd * 100, 4),
        "win_rate_pct": round(win_rate * 100, 2),
    }
