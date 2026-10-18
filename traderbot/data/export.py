import csv
import json
import re
from pathlib import Path

from traderbot.markets.market_data import fetch_ohlc_range, market_symbol
from traderbot.utils.bars import filter_bars_by_unix_range
from traderbot.utils.constants import SECONDS_PER_DAY
from traderbot.utils.resolution import resolution_minutes

CSV_FIELDS = [
    "symbol",
    "resolution",
    "timestamp",
    "datetime_utc",
    "open",
    "high",
    "low",
    "close",
    "volume",
]

_SAFE_TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def safe_export_token(value: object, *, field: str) -> str:
    """Return ``value`` only if it is safe to use in an export filename.

    Rejects path separators, parent-directory markers, and other characters
    that would let a job write outside ``output_dir``.
    """
    token = str(value).strip()
    if not token or token in {".", ".."} or not _SAFE_TOKEN_RE.match(token):
        raise ValueError(f"unsafe export {field}: {value!r}")
    return token


def load_jobs(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "jobs" in data:
        jobs = data["jobs"]
        default_days = data.get("days")
    elif isinstance(data, list):
        jobs = data
        default_days = None
    else:
        raise ValueError('JSON must be a list of jobs or {"jobs": [...], "days": N}')
    out = []
    for job in jobs:
        if "symbol" in job:
            symbol = job["symbol"]
        elif "src" in job and "dst" in job:
            symbol = market_symbol(job["src"], job["dst"])
        else:
            raise ValueError("each job needs symbol or src+dst")
        interval = job.get("interval") or job.get("resolution")
        if not interval:
            raise ValueError("each job needs interval or resolution")
        days = job.get("days", default_days)
        out.append({"symbol": symbol, "interval": interval, "days": days})
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _src_from_job_symbol(symbol: str) -> str | None:
    upper = symbol.strip().upper()
    if upper.endswith("USDT"):
        return upper[:-4].lower()
    if upper.endswith("IRT"):
        return upper[:-3].lower()
    return None


def _fetch_job_rows(
    job: dict,
    *,
    history_from_unix_seconds: int,
    history_to_unix_seconds: int,
) -> list[dict]:
    from traderbot.markets.exchange import normalize_live_exchange

    exchange = normalize_live_exchange(job.get("exchange") or "nobitex")
    resolution = job["interval"]
    if exchange == "hyperliquid":
        from traderbot.hyperliquid.market_data import fetch_hyperliquid_ohlc_range

        src = job.get("src")
        if not src:
            src = _src_from_job_symbol(str(job.get("symbol") or ""))
        if not src:
            raise ValueError("hyperliquid export job requires src or a USDT/IRT market symbol")
        return fetch_hyperliquid_ohlc_range(
            src=str(src),
            resolution=str(resolution),
            history_from_unix_seconds=history_from_unix_seconds,
            history_to_unix_seconds=history_to_unix_seconds,
        )
    symbol = job["symbol"]
    return fetch_ohlc_range(
        symbol=symbol,
        resolution=resolution,
        history_from_unix_seconds=history_from_unix_seconds,
        history_to_unix_seconds=history_to_unix_seconds,
    )


def run_export(
    jobs: list[dict],
    *,
    days: int,
    output_dir: Path,
    from_ts: int | None = None,
    to_ts: int | None,
    crypto_layout: bool = False,
) -> list[Path]:
    import time

    to_ts = to_ts or int(time.time())
    crypto_root: Path | None = None
    if crypto_layout:
        from traderbot.data.crypto_store import OHLC_SUBDIR, materialize_crypto_tree

        output_dir = output_dir.resolve()
        if output_dir.name == OHLC_SUBDIR:
            crypto_root = output_dir.parent
            output_dir = output_dir
        else:
            crypto_root = output_dir
            output_dir = output_dir / OHLC_SUBDIR
        output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for job in jobs:
        symbol = job["symbol"]
        resolution = job["interval"]
        job_days = job.get("days") or days
        history_from_unix_seconds = (
            from_ts if from_ts is not None else to_ts - job_days * SECONDS_PER_DAY
        )
        rows = _fetch_job_rows(
            job,
            history_from_unix_seconds=history_from_unix_seconds,
            history_to_unix_seconds=to_ts,
        )
        try:
            bar_minutes = resolution_minutes(resolution)
        except ValueError:
            bar_minutes = None
        if bar_minutes is not None:
            rows = filter_bars_by_unix_range(
                rows,
                end_unix_seconds=to_ts,
                bar_minutes=bar_minutes,
            )
        max_bars = job.get("max_bars")
        if max_bars is not None and int(max_bars) >= 1:
            rows = rows[-int(max_bars) :]
        if not rows:
            from traderbot.markets.exchange import normalize_live_exchange

            if normalize_live_exchange(job.get("exchange") or "nobitex") == "hyperliquid":
                from traderbot.hyperliquid.market_data import hyperliquid_export_empty_reason

                src = job.get("src") or _src_from_job_symbol(str(symbol))
                raise ValueError(
                    hyperliquid_export_empty_reason(str(src or symbol), resolution=str(resolution))
                )
            raise ValueError(f"{symbol} {resolution}: export returned 0 candles for the requested window")
        filename = f"{safe_export_token(symbol, field='symbol')}_{safe_export_token(resolution, field='resolution')}.csv"
        path = output_dir / filename
        write_csv(path, rows)
        written.append(path)
        venue = job.get("exchange") or "nobitex"
        print(f"{symbol} {resolution} ({venue}): {len(rows)} rows -> {path}")
    if written:
        manifest_dir = crypto_root if crypto_root is not None else output_dir
        _write_manifest(manifest_dir, written)
        if crypto_root is not None:
            materialize_crypto_tree(output_dir, crypto_root=crypto_root)
    return written


def _write_manifest(output_dir: Path, paths: list[Path]) -> None:
    symbols = sorted({p.stem.split("_")[0] for p in paths})
    manifest = {
        "sources": symbols,
        "files": [{"path": str(p.relative_to(output_dir)), "rows": _count_csv_rows(p)} for p in paths],
    }
    (output_dir / "export_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )


def _count_csv_rows(path: Path) -> int:
    with path.open(encoding="utf-8") as f:
        return max(0, sum(1 for _ in f) - 1)
