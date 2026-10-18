from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

MAX_LIVE_BATCH_COMBOS = 16
DEFAULT_LIVE_HORIZON = "60"


def resolved_horizons_for_live_run(horizons: Sequence[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in horizons:
        key = str(raw).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered if ordered else [DEFAULT_LIVE_HORIZON]


@dataclass(frozen=True)
class LiveMarketCombo:
    src: str
    dst: str
    interval: str
    symbol: str


@dataclass(frozen=True)
class LiveRunCombo:
    src: str
    dst: str
    interval: str
    symbol: str
    strategy_id: str


def market_combos_for_live_run(
    *,
    multi_run: bool,
    src: str,
    dst: str,
    market_symbol: str | None,
    batch_markets: Sequence[dict[str, Any]],
    horizons: Sequence[str],
) -> list[LiveMarketCombo]:
    intervals = resolved_horizons_for_live_run(horizons)
    if not multi_run:
        base_src = src.strip().lower()
        base_dst = dst.strip().lower()
        symbol = str(market_symbol or "")
        return [
            LiveMarketCombo(
                src=base_src,
                dst=base_dst,
                interval=str(resolution),
                symbol=symbol,
            )
            for resolution in intervals
        ]
    combos: list[LiveMarketCombo] = []
    for row in batch_markets:
        market = LiveMarketCombo(
            src=str(row["src"]).strip().lower(),
            dst=str(row["dst"]).strip().lower(),
            interval="",
            symbol=str(row["symbol"]),
        )
        for resolution in intervals:
            combos.append(
                LiveMarketCombo(
                    src=market.src,
                    dst=market.dst,
                    interval=str(resolution),
                    symbol=market.symbol,
                )
            )
    return combos


def strategy_ids_for_live_run(
    *,
    multi_strategy: bool,
    strategy_id: str,
    batch_strategy_ids: Sequence[str],
) -> list[str]:
    if not multi_strategy:
        return [strategy_id]
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in batch_strategy_ids:
        key = str(raw).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def build_live_run_combos(
    *,
    multi_run: bool,
    src: str,
    dst: str,
    market_symbol: str | None,
    batch_markets: Sequence[dict[str, Any]],
    horizons: Sequence[str],
    multi_strategy: bool,
    strategy_id: str,
    batch_strategy_ids: Sequence[str],
) -> list[LiveRunCombo]:
    markets = market_combos_for_live_run(
        multi_run=multi_run,
        src=src,
        dst=dst,
        market_symbol=market_symbol,
        batch_markets=batch_markets,
        horizons=horizons,
    )
    strategies = strategy_ids_for_live_run(
        multi_strategy=multi_strategy,
        strategy_id=strategy_id,
        batch_strategy_ids=batch_strategy_ids,
    )
    combos: list[LiveRunCombo] = []
    for market in markets:
        for sid in strategies:
            combos.append(
                LiveRunCombo(
                    src=market.src,
                    dst=market.dst,
                    interval=market.interval,
                    symbol=market.symbol,
                    strategy_id=sid,
                )
            )
    return combos


def combo_unique_key(combo: LiveRunCombo) -> str:
    return f"{combo.symbol}|{combo.interval}|{combo.strategy_id}"


def assert_unique_live_run_combos(combos: Sequence[LiveRunCombo]) -> None:
    keys = [combo_unique_key(row) for row in combos]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate live run combo")
