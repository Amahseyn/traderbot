from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from traderbot.export_csv import load_jobs
from traderbot.market_data import RESOLUTIONS, market_symbol

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_JOBS_PATH = REPO_ROOT / "export.jobs.5sources.json"


@dataclass(frozen=True, slots=True)
class MarketSpec:
    src: str
    dst: str
    symbol: str

    @property
    def label(self) -> str:
        return f"{self.src.upper()}/{self.dst.upper()}"


def list_supported_markets(jobs_path: Path | None = None) -> tuple[MarketSpec, ...]:
    """Unique markets from an export jobs file (default: five-source crypto set)."""
    path = jobs_path or DEFAULT_JOBS_PATH
    if not path.is_file():
        raise FileNotFoundError(f"jobs file not found: {path}")
    jobs = load_jobs(path)
    seen: set[str] = set[str]()
    out: list[MarketSpec] = []
    for job in jobs:
        symbol = str(job["symbol"]).upper()
        if symbol in seen:
            continue
        seen.add(symbol)
        out.append(market_spec_from_symbol(symbol))
    return tuple(out)


def market_spec_from_symbol(symbol: str) -> MarketSpec:
    sym = symbol.upper()
    if sym.endswith("IRT"):
        return MarketSpec(src=sym[:-3].lower(), dst="rls", symbol=sym)
    if sym.endswith("USDT"):
        return MarketSpec(src=sym[:-4].lower(), dst="usdt", symbol=sym)
    return MarketSpec(src=sym.lower(), dst="rls", symbol=sym)


def markets_catalog_dict(jobs_path: Path | None = None) -> dict:
    markets = list_supported_markets(jobs_path)
    return {
        "jobs_file": str(jobs_path or DEFAULT_JOBS_PATH),
        "markets": [asdict(m) | {"label": m.label} for m in markets],
        "udf_resolutions": list(RESOLUTIONS),
    }
