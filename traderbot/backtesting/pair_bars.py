from __future__ import annotations

from pathlib import Path
from typing import Any

from traderbot.backtesting import load_bars_csv
from traderbot.utils.pair_bars import align_bars_by_timestamp


def attach_hedge_bars_from_namespace(
    bars: list[dict[str, Any]],
    namespace: Any,
    *,
    primary_csv: Path,
) -> list[dict[str, Any]]:
    hedge_csv = getattr(namespace, "hedge_csv", None)
    if not hedge_csv:
        return bars
    hedge_path = Path(str(hedge_csv))
    if not hedge_path.is_absolute():
        hedge_path = primary_csv.parent / hedge_path
    hedge_bars = load_bars_csv(hedge_path)
    aligned = align_bars_by_timestamp(bars, hedge_bars)
    if not aligned:
        raise ValueError(f"No overlapping timestamps between {primary_csv} and {hedge_path}")
    return aligned
