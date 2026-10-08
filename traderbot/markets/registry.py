from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from traderbot.data.export import load_jobs
from traderbot.markets.market_data import BASE_URL, RESOLUTIONS, fetch_nobitex_market_symbols

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_JOBS_PATH = REPO_ROOT / "export.jobs.example.json"


@dataclass(frozen=True, slots=True)
class MarketSpec:
    src: str
    dst: str
    symbol: str

    @property
    def label(self) -> str:
        return f"{self.src.upper()}/{self.dst.upper()}"


def list_supported_markets(jobs_path: Path | None = None) -> list[MarketSpec]:
    """Unique markets from an export jobs file (default: export.jobs.example.json)."""
    path = jobs_path or DEFAULT_JOBS_PATH
    if not path.is_file():
        raise FileNotFoundError(f"jobs file not found: {path}")
    jobs = load_jobs(path)
    seen: set[str] = set()
    out: list[MarketSpec] = []
    for job in jobs:
        symbol = str(job["symbol"]).upper()
        if symbol in seen:
            continue
        seen.add(symbol)
        out.append(market_spec_from_symbol(symbol))
    return out


def market_spec_from_symbol(symbol: str) -> MarketSpec:
    sym = symbol.upper()
    if sym.endswith("IRT"):
        return MarketSpec(src=sym[:-3].lower(), dst="rls", symbol=sym)
    if sym.endswith("USDT"):
        return MarketSpec(src=sym[:-4].lower(), dst="usdt", symbol=sym)
    return MarketSpec(src=sym.lower(), dst="rls", symbol=sym)


def list_nobitex_markets() -> list[MarketSpec]:
    """Every market pair listed on Nobitex (public ``/market/stats``)."""
    return [market_spec_from_symbol(symbol) for symbol in fetch_nobitex_market_symbols()]


def markets_catalog_dict(jobs_path: Path | None = None) -> dict:
    if jobs_path is not None:
        markets = list_supported_markets(jobs_path)
        meta = {"jobs_file": str(jobs_path)}
    else:
        markets = list_nobitex_markets()
        meta = {"source": f"{BASE_URL.rstrip('/')}/market/stats"}
    return {
        **meta,
        "market_count": len(markets),
        "markets": [asdict(market) | {"label": market.label} for market in markets],
        "udf_resolutions": list(RESOLUTIONS),
    }
