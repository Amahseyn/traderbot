from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from traderbot.backtesting.validation import LeaderboardOptions, run_leakage_safe_leaderboard
from traderbot.data.export import write_csv
from traderbot.hyperliquid.market_data import (
    HYPERLIQUID_RESOLUTIONS,
    fetch_hyperliquid_perp_coins,
    fetch_hyperliquid_recent_closed_bars,
)

# Prefer liquid perps first when building a multi-market batch.
PREFERRED_HYPERLIQUID_COINS: tuple[str, ...] = (
    "BTC",
    "ETH",
    "SOL",
    "ARB",
    "AVAX",
    "DOGE",
    "LINK",
    "OP",
    "SUI",
    "WIF",
    "APT",
    "BNB",
    "PEPE",
    "TON",
    "JUP",
    "SEI",
    "TIA",
    "INJ",
    "NEAR",
    "FIL",
    "ATOM",
    "LTC",
    "ADA",
    "XRP",
    "BCH",
    "TRX",
    "UNI",
    "AAVE",
    "MKR",
    "CRV",
)


def resolve_batch_market_coins(
    *,
    limit: int,
    extra: list[str] | None = None,
) -> list[str]:
    if limit < 1:
        raise ValueError("limit must be >= 1")
    available = {coin.upper() for coin in fetch_hyperliquid_perp_coins()}
    ordered: list[str] = []
    for coin in PREFERRED_HYPERLIQUID_COINS:
        if coin in available and coin not in ordered:
            ordered.append(coin)
    for coin in extra or []:
        upper = coin.strip().upper()
        if upper in available and upper not in ordered:
            ordered.append(upper)
    for coin in sorted(available):
        if coin not in ordered:
            ordered.append(coin)
        if len(ordered) >= limit:
            break
    return [coin.lower() for coin in ordered[:limit]]


@dataclass
class LeaderboardBatchOptions:
    markets: list[str]
    resolutions: list[str]
    out_dir: Path
    max_bars: int = 2500
    cash: float = 10.0
    fee: float = 0.00045
    slippage: float = 0.0005
    execution: str = "next_open"
    test_tail_bars: int = 100
    validation_fraction: float = 0.25
    top_n: int = 3
    min_trades: int = 0
    max_combos: int = 128
    full_grid: bool = True


def run_leaderboard_batch(
    options: LeaderboardBatchOptions,
    *,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    emit = log or (lambda message: None)
    options.out_dir.mkdir(parents=True, exist_ok=True)
    runs: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    total_jobs = len(options.markets) * len(options.resolutions)
    job_index = 0

    for coin in options.markets:
        for resolution in options.resolutions:
            job_index += 1
            label = f"{coin.upper()}_{resolution}"
            emit(f"[{job_index}/{total_jobs}] {label} …")
            try:
                bars = fetch_hyperliquid_recent_closed_bars(
                    src=coin,
                    resolution=str(resolution),
                    max_bars=options.max_bars,
                )
                if len(bars) <= options.test_tail_bars + 32:
                    raise ValueError(f"insufficient bars ({len(bars)})")
                payload = run_leakage_safe_leaderboard(
                    LeaderboardOptions(
                        bars=bars,
                        test_tail_bars=options.test_tail_bars,
                        validation_fraction_of_pre_test=options.validation_fraction,
                        top_n=options.top_n,
                        cash=options.cash,
                        fee=options.fee,
                        slippage=options.slippage,
                        execution=options.execution,
                        min_trades=options.min_trades,
                        max_combos=options.max_combos,
                        full_grid=options.full_grid,
                        market_label=label,
                    ),
                )
                run_dir = options.out_dir / label
                run_dir.mkdir(parents=True, exist_ok=True)
                csv_path = run_dir / f"{label}.csv"
                write_csv(csv_path, bars)
                manifest_path = run_dir / "leaderboard_manifest.json"
                payload["source"] = {
                    "exchange": "hyperliquid",
                    "src": coin,
                    "resolution": str(resolution),
                    "max_bars_requested": options.max_bars,
                    "bars_fetched": len(bars),
                    "full_grid": options.full_grid,
                    "max_combos": options.max_combos,
                }
                payload["csv"] = str(csv_path)
                payload["manifest"] = str(manifest_path)
                manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                best_test = None
                if payload.get("top_strategies_test"):
                    best_test = max(
                        payload["top_strategies_test"],
                        key=lambda row: float(row["test"]["return_pct"]),
                    )
                runs.append(
                    {
                        "market": label,
                        "coin": coin,
                        "resolution": str(resolution),
                        "manifest": str(manifest_path),
                        "validation_winner": (
                            payload["all_strategies_validation_ranking"][0]
                            if payload.get("all_strategies_validation_ranking")
                            else None
                        ),
                        "best_test_strategy": best_test,
                    }
                )
            except Exception as exc:
                failures.append(
                    {
                        "market": label,
                        "coin": coin,
                        "resolution": str(resolution),
                        "error": str(exc),
                    }
                )
                emit(f"  failed: {exc}")

    master = {
        "exchange": "hyperliquid",
        "markets": options.markets,
        "resolutions": options.resolutions,
        "full_grid": options.full_grid,
        "max_combos": options.max_combos,
        "cash": options.cash,
        "test_tail_bars": options.test_tail_bars,
        "completed_runs": len(runs),
        "failed_runs": len(failures),
        "runs": runs,
        "failures": failures,
    }
    master_path = options.out_dir / "batch_leaderboard_manifest.json"
    master_path.write_text(json.dumps(master, indent=2), encoding="utf-8")
    master["manifest"] = str(master_path)
    return master


def default_batch_resolutions() -> list[str]:
    return list(HYPERLIQUID_RESOLUTIONS)
