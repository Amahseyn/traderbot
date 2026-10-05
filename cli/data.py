from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from traderbot.data.crypto_store import (
    default_crypto_root,
    materialize_crypto_tree,
    resolve_crypto_data_dir,
)
from traderbot.markets.market_data import RESOLUTIONS
from traderbot.markets.registry import DEFAULT_JOBS_PATH, markets_catalog_dict
from traderbot.markets.live_visualize import run_live_market_visualization
from traderbot.results.layout import default_live_markets_out
from traderbot.results.plots import (
    open_plots_in_viewer,
    results_plots_catalog,
    show_plots_interactive,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Crypto data layouts and live UDF market visualization.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    markets = sub.add_parser(
        "markets",
        help="List supported markets (from export jobs file; default five-source set)",
    )
    markets.add_argument(
        "--jobs",
        type=Path,
        default=None,
        help=f"Export jobs JSON (default: {DEFAULT_JOBS_PATH.name})",
    )

    live = sub.add_parser(
        "live",
        help="Fetch recent UDF candles for every supported market and write a dashboard PNG",
    )
    live.add_argument(
        "--interval",
        "--resolution",
        dest="resolution",
        default="60",
        choices=RESOLUTIONS,
        help="UDF candle size (default 60)",
    )
    live.add_argument(
        "--bars",
        type=int,
        default=96,
        help="Max recent closed bars per market (default 96)",
    )
    live.add_argument("--jobs", type=Path, default=None, help="Jobs file defining market list")
    live.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (visualizations/ + manifest)",
    )
    live.add_argument(
        "--show",
        action="store_true",
        help="Open interactive chart window (use with --poll-sec to refresh)",
    )
    live.add_argument(
        "--poll-sec",
        type=float,
        default=0.0,
        help="Re-fetch and redraw every N seconds (0 = one shot)",
    )
    live.add_argument(
        "--max-updates",
        type=int,
        default=None,
        help="Stop after N refresh cycles (for tests / bounded watch)",
    )
    live.add_argument(
        "--json",
        action="store_true",
        help="Print last-close manifest JSON only (skip matplotlib)",
    )

    horizons = sub.add_parser(
        "horizons",
        help="Copy legacy OHLC (if needed) and rebuild data/crypto/horizons/* from the latest bars",
    )
    horizons.add_argument(
        "--from",
        dest="from_dir",
        type=Path,
        default=None,
        help="OHLC directory (default: data/crypto/ohlc or data/multisource)",
    )
    horizons.add_argument(
        "--crypto-root",
        type=Path,
        default=None,
        help="Crypto data root (default: data/crypto)",
    )

    plots = sub.add_parser(
        "plots",
        help="List or open PNG charts from a prior run directory (compare, backtest, live)",
    )
    plots.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=None,
        help="Run directory; omit with --pick for interactive browser",
    )
    plots.add_argument(
        "--pick",
        action="store_true",
        help="Choose category, run, and strategy interactively (TTY)",
    )
    plots.add_argument(
        "--json",
        action="store_true",
        help="Print discovered plot paths as JSON",
    )
    plots.add_argument(
        "--open",
        action="store_true",
        help="Open each PNG in the system image viewer",
    )
    plots.add_argument(
        "--show",
        action="store_true",
        help="Display plots in an interactive matplotlib window",
    )

    args = parser.parse_args(argv)

    if args.command == "markets":
        print(json.dumps(markets_catalog_dict(args.jobs), indent=2))
        return

    if args.command == "live":
        out_dir = args.out or default_live_markets_out()
        try:
            manifest = run_live_market_visualization(
                resolution=args.resolution,
                max_bars=args.bars,
                out_dir=out_dir,
                jobs_path=args.jobs,
                show=args.show,
                poll_sec=args.poll_sec,
                max_updates=args.max_updates,
                json_only=args.json,
            )
        except FileNotFoundError as e:
            print(e, file=sys.stderr)
            sys.exit(1)
        except ImportError as e:
            print(e, file=sys.stderr)
            sys.exit(1)
        print(json.dumps(manifest, indent=2))
        if not args.json and manifest.get("visualization"):
            print(f"plots: {manifest['visualization']}", file=sys.stderr)
        return

    if args.command == "plots":
        plot_root = args.path
        if args.pick or plot_root is None:
            if not sys.stdin.isatty():
                print("data plots: pass a path or use --pick on an interactive terminal", file=sys.stderr)
                sys.exit(1)
            from cli.interactive.results_picker import pick_result_directory

            plot_root = pick_result_directory()
            if plot_root is None:
                sys.exit(1)
        try:
            catalog = results_plots_catalog(plot_root)
        except FileNotFoundError as e:
            print(e, file=sys.stderr)
            sys.exit(1)
        if args.json:
            print(json.dumps(catalog, indent=2))
            return
        plot_paths = [Path(p) for p in catalog["plots"]]
        if not plot_paths:
            print(f"no PNG charts found under {args.path}", file=sys.stderr)
            sys.exit(1)
        for path in plot_paths:
            print(path)
        if args.open:
            try:
                open_plots_in_viewer(plot_paths)
            except RuntimeError as e:
                print(e, file=sys.stderr)
                sys.exit(1)
        if args.show:
            try:
                show_plots_interactive(plot_paths)
            except ImportError as e:
                print(e, file=sys.stderr)
                sys.exit(1)
        return

    if args.command == "horizons":
        source = resolve_crypto_data_dir(args.from_dir)
        if source is None:
            print(
                "no OHLC CSVs found; run: traderbot export --jobs export.jobs.5sources.json --out data/crypto",
                file=sys.stderr,
            )
            sys.exit(1)
        root = materialize_crypto_tree(
            source,
            crypto_root=args.crypto_root or default_crypto_root(),
        )
        manifest = root / "horizon_manifest.json"
        if manifest.is_file():
            print(json.dumps(json.loads(manifest.read_text(encoding="utf-8")), indent=2))
        else:
            print(json.dumps({"crypto_root": str(root)}, indent=2))
        return
