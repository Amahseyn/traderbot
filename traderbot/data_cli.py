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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build crypto dataset layouts on disk.")
    sub = parser.add_subparsers(dest="command", required=True)

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

    args = parser.parse_args(argv)

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
