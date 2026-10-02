import argparse
import csv
import json
import sys
from pathlib import Path

from traderbot.market_data import fetch_ohlc_range, market_symbol

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
        start = from_ts if from_ts is not None else to_ts - job_days * 86400
        rows = fetch_ohlc_range(
            symbol=symbol,
            resolution=resolution,
            from_ts=start,
            to_ts=to_ts,
        )
        filename = f"{symbol}_{resolution}.csv"
        path = output_dir / filename
        write_csv(path, rows)
        written.append(path)
        print(f"{symbol} {resolution}: {len(rows)} rows -> {path}")
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Export Nobitex OHLC data to CSV (public API)")
    parser.add_argument(
        "--jobs",
        type=Path,
        help='JSON file: [{"src":"btc","dst":"rls","interval":"D"}, ...] or {"jobs":[],"days":90}',
    )
    parser.add_argument("--symbol", help="Single market symbol, e.g. BTCIRT")
    parser.add_argument("--src", help="With --dst, build symbol (btc + rls)")
    parser.add_argument("--dst", help="rls or usdt")
    parser.add_argument("--interval", "--resolution", dest="interval", help="1, 15, 60, D, ...")
    parser.add_argument("--days", type=int, default=30, help="History length (default 30)")
    parser.add_argument("--out", type=Path, default=Path("data"), help="Output directory")
    parser.add_argument(
        "--crypto-layout",
        action="store_true",
        help="Write data/crypto/ohlc plus complete per-horizon folders under data/crypto/horizons/",
    )
    args = parser.parse_args(argv)

    if args.jobs:
        jobs = load_jobs(args.jobs)
        crypto_layout = args.crypto_layout or args.out.name == "crypto"
        run_export(
            jobs,
            days=args.days,
            output_dir=args.out,
            to_ts=None,
            crypto_layout=crypto_layout,
        )
        return

    if args.symbol and args.interval:
        jobs = [{"symbol": args.symbol.upper(), "interval": args.interval, "days": args.days}]
    elif args.src and args.dst and args.interval:
        jobs = [
            {
                "symbol": market_symbol(args.src, args.dst),
                "interval": args.interval,
                "days": args.days,
            }
        ]
    else:
        parser.print_help()
        print("\nExample: traderbot export --src btc --dst rls --interval D --days 90", file=sys.stderr)
        sys.exit(2)

    crypto_layout = args.crypto_layout or args.out.name == "crypto"
    run_export(
        jobs,
        days=args.days,
        output_dir=args.out,
        to_ts=None,
        crypto_layout=crypto_layout,
    )


if __name__ == "__main__":
    main()
