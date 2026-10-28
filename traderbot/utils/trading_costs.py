from __future__ import annotations

import os
import re
from pathlib import Path

from traderbot.markets.execution_costs import (
    HYPERLIQUID_PERP_MAKER_FEE,
    HYPERLIQUID_PERP_TAKER_FEE,
    HYPERLIQUID_TAKER_SLIPPAGE,
    execution_cost_profile,
)

# Default backtest costs match Hyperliquid perp tier-0 taker (market-style fills).
_DEFAULT_FEE = HYPERLIQUID_PERP_TAKER_FEE
# Taker fills cross the spread: 0.05% per fill (docs/live-trading.md). Override with
# TRADERBOT_DEFAULT_SLIPPAGE_RATE. Nobitex uses its own execution_cost_profile slippage.
_DEFAULT_SLIPPAGE = HYPERLIQUID_TAKER_SLIPPAGE


def _rate_from_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return float(raw)


DEFAULT_TRADE_FEE_RATE = _rate_from_env("TRADERBOT_DEFAULT_FEE_RATE", _DEFAULT_FEE)
DEFAULT_SLIPPAGE_RATE = _rate_from_env("TRADERBOT_DEFAULT_SLIPPAGE_RATE", _DEFAULT_SLIPPAGE)
DEFAULT_MAKER_FEE_RATE = HYPERLIQUID_PERP_MAKER_FEE
DEFAULT_BACKTEST_EXECUTION = "next_open"

# Nobitex spot markets quote in IRT (rial/toman). Hyperliquid perps in this repo are named COINUSDT.
_NOBITEX_SYMBOL_RE = re.compile(r"(IRT|RLS)(_[0-9A-Z]+)?$", re.IGNORECASE)


def infer_exchange(source: str | Path | None) -> str | None:
    """Best-effort venue from a symbol or CSV name (``BTCIRT_1.csv`` → nobitex).

    Returns ``None`` when the name is ambiguous (e.g. ``BTCUSDT`` exists on both venues);
    callers then fall back to the default venue (Hyperliquid).
    """
    if source is None:
        return None
    text = str(source).strip()
    if not text:
        return None
    parts = [p for p in re.split(r"[\\/]", text) if p]
    for part in reversed(parts):
        low = part.lower()
        if low in ("nobitex", "hyperliquid"):
            return low
        if "hyperliquid" in low:
            return "hyperliquid"
        if "nobitex" in low:
            return "nobitex"
    stem = Path(parts[-1]).stem if parts else text
    if _NOBITEX_SYMBOL_RE.search(stem.upper()):
        return "nobitex"
    return None


def backtest_cost_rates(
    exchange: str | None = None,
    *,
    fee_role: str = "taker",
    market_kind: str = "perp",
) -> tuple[float, float]:
    """Return (fee_rate, slippage_rate) for a venue; falls back to global defaults."""
    if exchange is None:
        if fee_role == "maker":
            return DEFAULT_MAKER_FEE_RATE, 0.0
        return DEFAULT_TRADE_FEE_RATE, DEFAULT_SLIPPAGE_RATE
    role = "maker" if fee_role == "maker" else "taker"
    kind = "spot" if market_kind == "spot" else "perp"
    profile = execution_cost_profile(exchange, fee_role=role, market_kind=kind)  # type: ignore[arg-type]
    return profile.fee_rate, profile.slippage_rate


def maker_fee_rate(exchange: str | None = None, *, market_kind: str = "perp") -> float:
    """Maker fee for resting limit fills (post-only entries, take-profit limits)."""
    return backtest_cost_rates(exchange, fee_role="maker", market_kind=market_kind)[0]


def resolve_cost_rates(
    *,
    exchange: str | None = None,
    source: str | Path | None = None,
    fee: float | None = None,
    slippage: float | None = None,
    fee_role: str = "taker",
) -> tuple[float, float]:
    """Explicit ``fee`` / ``slippage`` win; otherwise use the venue's cost profile.

    The venue is ``exchange`` when given, else inferred from ``source`` (CSV path or symbol),
    else the global default (Hyperliquid perp taker).
    """
    venue = exchange or infer_exchange(source)
    if venue is not None:
        market_kind = "spot" if venue == "nobitex" else "perp"
        profile_fee, profile_slip = backtest_cost_rates(venue, fee_role=fee_role, market_kind=market_kind)
    else:
        profile_fee, profile_slip = backtest_cost_rates(None, fee_role=fee_role)
    return (
        float(fee) if fee is not None else profile_fee,
        float(slippage) if slippage is not None else profile_slip,
    )


def roundtrip_cost_rate(
    *,
    exchange: str | None = None,
    source: str | Path | None = None,
    fee: float | None = None,
    slippage: float | None = None,
    maker_entry: bool = False,
) -> float:
    """Total friction for one entry + one exit, as a fraction of notional.

    A market roundtrip pays ``(fee + slippage)`` on both legs — 0.190% on Hyperliquid perp
    taker and 0.900% on Nobitex spot retail, versus a 0.04–0.08% median 1-minute candle.
    ``maker_entry`` swaps the entry leg for a resting post-only fill: maker fee, no slippage.
    """
    fee_rate, slippage_rate = resolve_cost_rates(
        exchange=exchange,
        source=source,
        fee=fee,
        slippage=slippage,
    )
    if not maker_entry:
        return 2.0 * (fee_rate + slippage_rate)
    venue = exchange or infer_exchange(source)
    market_kind = "spot" if venue == "nobitex" else "perp"
    return maker_fee_rate(venue, market_kind=market_kind) + fee_rate + slippage_rate


def roundtrip_cost_pct(
    *,
    exchange: str | None = None,
    source: str | Path | None = None,
    fee: float | None = None,
    slippage: float | None = None,
    maker_entry: bool = False,
) -> float:
    """Same as :func:`roundtrip_cost_rate`; the strategy knob it feeds is named ``_pct``."""
    return roundtrip_cost_rate(
        exchange=exchange,
        source=source,
        fee=fee,
        slippage=slippage,
        maker_entry=maker_entry,
    )


def default_roundtrip_cost_pct(*, maker_entry: bool = False) -> float:
    """Roundtrip friction on the repo default venue (Hyperliquid perp)."""
    return roundtrip_cost_pct(exchange="hyperliquid", maker_entry=maker_entry)


def _source_for_options(options: object) -> str | Path | None:
    for attr in ("csv_path", "csv_dir"):
        value = getattr(options, attr, None)
        if value:
            return value
    paths = getattr(options, "csv_paths", None)
    if paths:
        return paths[0]
    bars = getattr(options, "bars", None)
    if bars:
        first = bars[0]
        if isinstance(first, dict) and first.get("symbol"):
            return str(first["symbol"])
    label = getattr(options, "market_label", None)
    return label or None


class ResolvesCostRates:
    """Dataclass mixin: ``fee`` / ``slippage`` left as ``None`` resolve to per-exchange costs.

    The venue is the dataclass ``exchange`` field when present, else inferred from the CSV
    path / bar symbol, else Hyperliquid perp taker (the repo default venue).
    """

    def __post_init__(self) -> None:  # noqa: D401 - dataclass hook
        fee, slippage = resolve_cost_rates(
            exchange=getattr(self, "exchange", None),
            source=_source_for_options(self),
            fee=getattr(self, "fee", None),
            slippage=getattr(self, "slippage", None),
        )
        self.fee = fee  # type: ignore[attr-defined]
        self.slippage = slippage  # type: ignore[attr-defined]


def optional_rate(raw: object) -> float | None:
    """Parse a fee/slippage field from a job body; blank means "use the venue profile"."""
    if raw in (None, ""):
        return None
    return float(raw)  # type: ignore[arg-type]


# Known (taker, maker) fee pairs so a run configured with only the taker fee still charges
# the venue's maker fee on resting limit fills.
_MAKER_FOR_TAKER: tuple[tuple[float, float], ...] = (
    (HYPERLIQUID_PERP_TAKER_FEE, HYPERLIQUID_PERP_MAKER_FEE),
    (0.0007, 0.0004),  # Hyperliquid spot
    (0.0035, 0.0025),  # Nobitex retail
)


def maker_fee_for(taker_fee: float) -> float:
    """Maker fee paired with ``taker_fee``; unknown tiers conservatively reuse the taker fee."""
    for taker, maker in _MAKER_FOR_TAKER:
        if abs(float(taker_fee) - taker) < 1e-12:
            return maker
    return float(taker_fee)
