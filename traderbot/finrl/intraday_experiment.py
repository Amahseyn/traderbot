"""Native Hyperliquid intraday EMA experiment (ported from FinRL-Trading).

Upstream FinRL ran this as a subprocess script (``scripts/run_hyperliquid_intraday_experiment.py``)
against its own ``src.data.hyperliquid_fetcher``. traderbot now performs the
same experiment in-process, using traderbot's Hyperliquid candles and the
vendored, point-in-time-correct intraday engine.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from traderbot.finrl.intraday_engine import run_intraday_backtest
from traderbot.hyperliquid.market_data import fetch_hyperliquid_recent_closed_bars

HyperliquidPErperTakerFee = 0.00045

_OHLC_COLUMNS = ("open", "high", "low", "close", "volume")


def bars_to_ohlcv_frame(bars: list[dict[str, Any]]) -> pd.DataFrame:
    """Build an OHLCV frame indexed by UTC bar close timestamp."""
    if not bars:
        return pd.DataFrame(columns=list(_OHLC_COLUMNS))
    frame = pd.DataFrame(bars)
    index = pd.to_datetime(
        [int(row["timestamp"]) for row in bars], unit="s", utc=True
    )
    ohlcv = frame[list(_OHLC_COLUMNS)].astype(float)
    ohlcv.index = index
    return ohlcv


def run_hyperliquid_intraday_experiment(
    *,
    coin: str,
    intervals: list[str],
    max_bars: int,
    out_dir: Path,
    fee_per_side: float = HyperliquidPErperTakerFee,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Fetch recent closed bars per interval and run the intraday EMA backtest."""
    coin = coin.strip().upper()
    report: dict[str, Any] = {"coin": coin, "intervals": {}, "platform": "traderbot"}
    for resolution in intervals:
        bars = fetch_hyperliquid_recent_closed_bars(
            src=coin.lower(), resolution=resolution, max_bars=max_bars
        )
        if not bars:
            raise RuntimeError(f"No bars for {coin} @ {resolution}")
        ohlcv = bars_to_ohlcv_frame(bars)
        result = run_intraday_backtest(
            ohlcv, resolution=resolution, fee_per_side=fee_per_side
        )
        report["intervals"][resolution] = {
            "bars": result.bars,
            "trades": result.trades,
            "window_metrics_not_annualized": result.window,
            "sharpe_per_bar": round(result.sharpe, 4),
            "meta": result.meta,
        }
        if log is not None:
            log(f"FinRL intraday {coin} {resolution}m: trades={result.trades} sharpe/bar={result.sharpe:.4f}")

    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"intraday_experiment_{coin}.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report
