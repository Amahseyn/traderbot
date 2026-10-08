from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from traderbot.backtesting.compare_session import StrategyCompareOptions, run_strategy_compare
from traderbot.data.crypto_store import resolve_crypto_1h_csv_paths
from traderbot.backtesting import load_bars_csv
from traderbot.data.export import run_export
from traderbot.markets.market_data import market_symbol as build_market_symbol
from traderbot.utils.bars import filter_bars_by_unix_range
from traderbot.utils.resolution import resolution_from_csv_path, resolution_minutes


def _bar_minutes_for_csv(csv_path: Path, body: dict[str, Any]) -> int:
    resolution = resolution_from_csv_path(csv_path.name)
    return int(body.get("bar_minutes") or resolution_minutes(resolution) or 60)


def _slice_bars_for_run_window(
    bars: list[dict[str, Any]],
    body: dict[str, Any],
    *,
    bar_minutes: int,
    csv_path: Path,
) -> list[dict[str, Any]]:
    start_unix_seconds = body.get("run_start_unix_seconds")
    end_unix_seconds = body.get("run_end_unix_seconds")
    if start_unix_seconds is None and end_unix_seconds is None:
        return bars
    filtered = filter_bars_by_unix_range(
        bars,
        start_unix_seconds=start_unix_seconds,
        end_unix_seconds=end_unix_seconds,
        bar_minutes=bar_minutes,
    )
    if not filtered:
        raise ValueError(f"run window has no bars for {csv_path.name}")
    return filtered


def _csv_paths_from_dataset_rows(rows: list[dict[str, Any]]) -> list[Path]:
    paths: list[Path] = []
    for row in rows:
        repo_path = row.get("repo_path")
        if not repo_path:
            continue
        path = Path(str(repo_path))
        if path.is_file():
            paths.append(path)
    return paths


def run_custom_research(body: dict[str, Any], *, log: Any = print) -> dict[str, Any]:
    """
    End-to-end research job: optional single-market export and strategy compare.

    Body keys (see job_resolvers.resolve_custom_research_body):
    export_market_symbol (+interval), export_market_symbols × export_intervals,
    export_days, dataset_ids, use_all_hourly_files,
    compare_strategies, max_strategies, strategy_ids, ...
    """
    summary: dict[str, Any] = {"steps": []}

    export_paths: list[Path] = []
    export_jobs: list[dict[str, Any]] = [dict(item) for item in body.get("export_jobs") or []]
    export_fields = body.get("export_fields")
    if export_fields and not export_jobs:
        export_jobs.append(dict(export_fields))
    if export_jobs:
        jobs: list[dict[str, Any]] = []
        first_out = str(export_jobs[0].get("out") or "data")
        first_crypto_layout = bool(export_jobs[0].get("crypto_layout"))
        export_days = int(body.get("export_days") or 30)
        for export_job in export_jobs:
            src = export_job.get("src")
            dst = export_job.get("dst")
            interval = export_job.get("interval")
            if not src or not dst or not interval:
                raise ValueError("export jobs require src, dst, and interval")
            jobs.append(
                {
                    "symbol": build_market_symbol(str(src), str(dst)),
                    "interval": str(interval),
                    "days": int(export_job.get("days") or export_days),
                    "max_bars": export_job.get("max_bars"),
                }
            )
        def _combo_label(job: dict[str, Any]) -> str:
            label = f"{job['symbol']}:{job['interval']}:{job['days']}d"
            if job.get("max_bars") is not None:
                label += f"/{job['max_bars']}bars"
            return label

        combo_label = ", ".join(_combo_label(job) for job in jobs)
        log(f"custom: exporting {len(jobs)} market × horizon combo(s): {combo_label}", flush=True)
        try:
            written = run_export(
                jobs,
                days=export_days,
                output_dir=Path(first_out),
                to_ts=None,
                crypto_layout=first_crypto_layout,
            )
        except Exception as exc:
            raise ValueError(f"export failed for [{combo_label}]: {exc}") from exc
        export_paths.extend(written)
        summary["export_markets"] = [
            {
                "symbol": job["symbol"],
                "interval": job["interval"],
                "days": job["days"],
                "max_bars": job.get("max_bars"),
            }
            for job in jobs
        ]
        summary["steps"].append({"step": "export_markets", "csv_count": len(written)})

    csv_paths: list[Path] = []
    for path in export_paths:
        if path.is_file() and path not in csv_paths:
            csv_paths.append(path)
    if body.get("dataset_rows"):
        csv_paths.extend(_csv_paths_from_dataset_rows(list(body["dataset_rows"])))
    if body.get("use_all_hourly_files"):
        for path in resolve_crypto_1h_csv_paths(all_assets=True):
            if path not in csv_paths:
                csv_paths.append(path)
    if not csv_paths:
        raise ValueError("select at least one dataset or enable export / all hourly files")

    log(f"custom: {len(csv_paths)} price file(s)", flush=True)

    if not bool(body.get("compare_strategies")):
        raise ValueError("enable strategy compare")

    strategy_ids = body.get("strategy_ids")
    strategy_id_set = frozenset(str(item) for item in strategy_ids) if strategy_ids else None
    max_strategies = body.get("max_strategies")
    if max_strategies is not None:
        max_strategies = int(max_strategies)

    from lab.tasks import _strategy_namespace_from_body

    mode = str(body.get("compare_mode") or "strategies")
    namespace = _strategy_namespace_from_body(body)
    compare_results: list[dict[str, Any]] = []
    for index, csv_path in enumerate(csv_paths, start=1):
        log(f"custom: compare [{index}/{len(csv_paths)}] {csv_path.name}", flush=True)
        try:
            payload = run_strategy_compare(
                StrategyCompareOptions(
                    csv_path=csv_path,
                    visualize=bool(body.get("visualize", True)),
                    cash=float(body.get("cash") or 10_000.0),
                    fee=float(body.get("fee") or 0.0),
                    slippage=float(body.get("slippage") or 0.0),
                    execution=str(body.get("execution") or "close"),
                    vectorbt=bool(body.get("vectorbt")),
                    strategy_namespace=namespace,
                    mode=mode,
                    strategy_ids=strategy_id_set,
                    max_strategies=max_strategies,
                    run_start_unix_seconds=body.get("run_start_unix_seconds"),
                    run_end_unix_seconds=body.get("run_end_unix_seconds"),
                    use_optimized_strategy_params=bool(body.get("use_optimized_strategy_params", True)),
                ),
                log=log,
            )
        except ValueError as exc:
            if "No bars in CSV" not in str(exc):
                raise
            log(f"custom: skip {csv_path.name}: {exc}", flush=True)
            compare_results.append({"csv": str(csv_path), "skipped": True, "reason": str(exc)})
            continue
        compare_results.append({"csv": str(csv_path), "best_strategy_id": payload.get("best_strategy_id")})
    succeeded = [entry for entry in compare_results if not entry.get("skipped")]
    if not succeeded:
        reasons = "; ".join(str(entry.get("reason", entry.get("csv"))) for entry in compare_results)
        raise ValueError(f"no dataset left bars in the run window: {reasons}")
    summary["compare"] = compare_results
    summary["steps"].append(
        {"step": "compare", "datasets": len(succeeded), "skipped": len(compare_results) - len(succeeded)}
    )

    log(json.dumps(summary, indent=2), flush=True)
    return summary
