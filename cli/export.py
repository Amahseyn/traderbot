import argparse
import sys
from pathlib import Path

from traderbot.data.export import load_jobs, run_export
from traderbot.markets.market_data import market_symbol


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
