from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lab.store import default_database_path, fetch_dashboard_stats, open_database
from lab.store.database import init_database
from lab.store.sync import sync_results_tree


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Traderbot Lab — SQLite store and JSON API for the web UI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init_cmd = sub.add_parser("init", help="Create or migrate the database schema")
    init_cmd.add_argument(
        "--db",
        type=Path,
        default=None,
        help=f"Database path (default: {default_database_path()})",
    )

    sync_cmd = sub.add_parser("sync", help="Backfill store from on-disk result files")
    sync_cmd.add_argument(
        "--root",
        type=Path,
        default=Path("results"),
        help="Root directory to scan (default: results/)",
    )
    sync_cmd.add_argument("--db", type=Path, default=None)

    stats_cmd = sub.add_parser("stats", help="Print dashboard counters as JSON")
    stats_cmd.add_argument("--db", type=Path, default=None)

    serve_cmd = sub.add_parser("serve", help="Start the Lab JSON API (requires pip install -e '.[ui]')")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=8765)
    serve_cmd.add_argument("--db", type=Path, default=None)
    serve_cmd.add_argument("--reload", action="store_true", help="Dev auto-reload")

    args = parser.parse_args(argv)

    if args.command == "init":
        connection = open_database(args.db)
        init_database(connection)
        from lab.store.catalog import backfill_datasets, ensure_market_catalog

        backfill_datasets(connection)
        ensure_market_catalog(connection)
        connection.commit()
        connection.close()
        print(json.dumps({"database": str(args.db or default_database_path()), "status": "ready"}, indent=2))
        return

    if args.command == "sync":
        counts = sync_results_tree(args.root.resolve(), database_path=args.db)
        print(json.dumps({"root": str(args.root), "indexed": counts}, indent=2))
        return

    if args.command == "stats":
        connection = open_database(args.db)
        try:
            print(json.dumps(fetch_dashboard_stats(connection), indent=2))
        finally:
            connection.close()
        return

    if args.command == "serve":
        try:
            import uvicorn
        except ImportError:
            print("Install UI dependencies: pip install -e '.[ui]'", file=sys.stderr)
            sys.exit(1)
        connection = open_database(args.db)
        init_database(connection)
        from lab.store.catalog import backfill_datasets, ensure_market_catalog

        backfill_datasets(connection)
        ensure_market_catalog(connection)
        connection.commit()
        connection.close()
        from lab.app import create_app

        app = create_app(database_path=args.db)
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            reload=args.reload,
            access_log=False,
        )
        return
