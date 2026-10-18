from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any

from traderbot.backtesting.compare_session import (
    StrategyCompareOptions,
    run_strategy_compare,
    strategy_ids_for_compare,
)
from traderbot.backtesting.research_windows import (
    ResearchWindowError,
    assert_optimize_sweep_coverage,
    preflight_research_csv_paths,
)
from traderbot.backtesting.robust_defaults import DEFAULT_HOLDOUT_FRACTION
from traderbot.data.crypto_store import resolve_crypto_1h_csv_paths
from traderbot.data.export import run_export
from traderbot.markets.market_data import market_symbol as build_market_symbol
from traderbot.utils.bars import filter_bars_by_unix_range
from traderbot.utils.resolution import resolution_from_csv_path, resolution_minutes
from traderbot.utils.trading_costs import (
    DEFAULT_BACKTEST_EXECUTION,
    DEFAULT_SLIPPAGE_RATE,
    DEFAULT_TRADE_FEE_RATE,
)


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


def _optimize_holdout_tail_bars(bar_count: int, body: dict[str, Any]) -> int | None:
    raw = body.get("optimize_holdout_tail_bars")
    if raw in (None, ""):
        raw = body.get("holdout_tail_bars")
    if raw not in (None, ""):
        holdout = int(raw)
        return holdout if holdout >= 1 else None
    if bar_count <= 10:
        return None
    return max(1, int(bar_count * DEFAULT_HOLDOUT_FRACTION))


def _log_file_failure(log: Any, phase: str, label: str, exc: BaseException) -> None:
    log(f"custom: {phase} failed {label}: {type(exc).__name__}: {exc}", flush=True)
    trace = traceback.format_exc().strip()
    if trace and trace != "NoneType: None":
        for line in trace.splitlines():
            log(f"custom:   {line}", flush=True)


def _failure_rows(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in entries if row.get("skipped") or row.get("failed")]


def _log_failure_summary(log: Any, summary: dict[str, Any]) -> None:
    lines: list[str] = []
    for row in summary.get("export_failures") or []:
        job = row.get("job") or {}
        symbol = job.get("symbol") or job.get("src") or "?"
        interval = job.get("interval") or "?"
        lines.append(f"export {symbol}:{interval} — {row.get('reason', 'unknown')}")
    for row in _failure_rows(list(summary.get("optimize") or [])):
        lines.append(
            f"optimize {Path(str(row.get('csv', '?'))).name}:{row.get('strategy_id', '?')} — "
            f"{row.get('reason', 'skipped')}"
        )
    for row in _failure_rows(list(summary.get("compare") or [])):
        lines.append(f"compare {Path(str(row.get('csv', '?'))).name} — {row.get('reason', 'skipped')}")
    if not lines:
        return
    log(f"custom: {len(lines)} file/combo failure(s) recorded (see steps above):", flush=True)
    for line in lines:
        log(f"custom:   · {line}", flush=True)


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
                    "src": str(src),
                    "dst": str(dst),
                    "exchange": str(export_job.get("exchange") or "nobitex"),
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
        export_failures: list[dict[str, Any]] = []
        for job in jobs:
            label = _combo_label(job)
            try:
                written = run_export(
                    [job],
                    days=int(job.get("days") or export_days),
                    output_dir=Path(first_out),
                    to_ts=None,
                    crypto_layout=first_crypto_layout,
                )
            except Exception as exc:
                _log_file_failure(log, "export", f"[{label}]", exc)
                export_failures.append({"job": job, "reason": str(exc), "error_type": type(exc).__name__})
                continue
            export_paths.extend(written)
            log(f"custom: export ok [{label}] → {len(written)} file(s)", flush=True)
        if export_failures:
            summary["export_failures"] = export_failures
        summary["export_markets"] = [
            {
                "symbol": job["symbol"],
                "interval": job["interval"],
                "days": job["days"],
                "max_bars": job.get("max_bars"),
            }
            for job in jobs
        ]
        summary["steps"].append(
            {
                "step": "export_markets",
                "csv_count": len(export_paths),
                "failed": len(export_failures),
            }
        )

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
    strategy_namespace = _strategy_namespace_from_body(body)
    use_optimized = bool(body.get("use_optimized_strategy_params", True))
    optimize_before = bool(body.get("optimize_before_compare"))
    apply_sweep_winner = bool(body.get("apply_sweep_winner")) or optimize_before
    # Effective per-file run start (may be auto-derived when the requested start has no
    # leading bars). Compare must reuse it so it evaluates the same window the optimizer trained for.
    effective_run_start: dict[Path, int | None] = {}
    if optimize_before:
        use_optimized = True

    if optimize_before:
        from lab.sweep_job import run_recorded_strategy_sweep

        try:
            strategies_to_optimize = strategy_ids_for_compare(
                mode,
                strategy_ids=strategy_id_set,
                max_strategies=max_strategies,
            )
        except ValueError as exc:
            raise ValueError(f"optimize before compare: {exc}") from exc
        try:
            research_windows = preflight_research_csv_paths(
                csv_paths,
                body,
                strategy_namespace,
                strategy_ids=strategies_to_optimize,
            )
        except ResearchWindowError as exc:
            raise ValueError(str(exc)) from exc
        windows_by_csv = dict(zip(csv_paths, research_windows))
        for path, windows in windows_by_csv.items():
            effective_run_start[path] = windows.run_start_unix_seconds
            if windows.auto_split:
                label = f"{windows.symbol or path.stem}:{windows.resolution or windows.bar_minutes}"
                log(
                    f"custom: auto walk-forward split {label}: train {len(windows.train_bars)} / "
                    f"eval {len(windows.eval_bars)} bars (run_start={windows.run_start_unix_seconds})",
                    flush=True,
                )
        sweep_results: list[dict[str, Any]] = []
        log(
            f"custom: optimize {len(strategies_to_optimize)} strategy(ies) on {len(csv_paths)} file(s)",
            flush=True,
        )
        for csv_path in csv_paths:
            windows = windows_by_csv[csv_path]
            train_bars = windows.train_bars
            if not train_bars:
                log(f"custom: optimize skip {csv_path.name}: no train bars", flush=True)
                continue
            holdout_tail_bars = _optimize_holdout_tail_bars(len(train_bars), body)
            market_label = f"{windows.symbol or csv_path.stem}:{windows.resolution or windows.bar_minutes}"
            selection_label = str(body.get("optimize_selection_mode") or "validation")
            log(
                f"custom: optimize train {len(train_bars)} bars for {market_label} "
                f"(selection={selection_label})",
                flush=True,
            )
            for strategy_id in strategies_to_optimize:
                sweep_body = {
                    **body,
                    "strategy_id": strategy_id,
                    "holdout_tail_bars": holdout_tail_bars,
                    "run_start_unix_seconds": windows.run_start_unix_seconds,
                }
                try:
                    payload = run_recorded_strategy_sweep(
                        sweep_body,
                        csv_path,
                        bars=train_bars,
                        log=log,
                    )
                except Exception as exc:
                    if holdout_tail_bars is not None and isinstance(exc, ValueError):
                        sweep_body["holdout_tail_bars"] = None
                        try:
                            payload = run_recorded_strategy_sweep(
                                sweep_body,
                                csv_path,
                                bars=train_bars,
                                log=log,
                            )
                        except Exception as retry_exc:
                            _log_file_failure(
                                log,
                                "optimize",
                                f"{strategy_id} on {csv_path.name}",
                                retry_exc,
                            )
                            sweep_results.append(
                                {
                                    "csv": str(csv_path),
                                    "strategy_id": strategy_id,
                                    "skipped": True,
                                    "reason": str(retry_exc),
                                }
                            )
                            continue
                    else:
                        _log_file_failure(log, "optimize", f"{strategy_id} on {csv_path.name}", exc)
                        sweep_results.append(
                            {
                                "csv": str(csv_path),
                                "strategy_id": strategy_id,
                                "skipped": True,
                                "reason": str(exc),
                            }
                        )
                        continue
                test_summary = payload.get("test") if isinstance(payload.get("test"), dict) else None
                sweep_results.append(
                    {
                        "csv": str(csv_path),
                        "symbol": windows.symbol,
                        "resolution": windows.resolution,
                        "strategy_id": strategy_id,
                        "train_bars": len(train_bars),
                        "eval_bars": len(windows.eval_bars),
                        "run_start_unix_seconds": windows.run_start_unix_seconds,
                        "auto_split": windows.auto_split,
                        "best_params": payload.get("best_params"),
                        "rank_by": payload.get("rank_by"),
                        "selection_mode": payload.get("selection_mode_applied")
                        or payload.get("selection_mode"),
                        "test_return_pct": test_summary.get("return_pct") if test_summary else None,
                    }
                )
        try:
            assert_optimize_sweep_coverage(csv_paths, strategies_to_optimize, sweep_results)
        except ResearchWindowError as exc:
            raise ValueError(str(exc)) from exc
        summary["optimize"] = sweep_results
        succeeded_sweeps = [row for row in sweep_results if not row.get("skipped")]
        summary["steps"].append(
            {
                "step": "optimize",
                "sweeps": len(succeeded_sweeps),
                "skipped": len(sweep_results) - len(succeeded_sweeps),
                "markets": len(csv_paths),
                "strategies": len(strategies_to_optimize),
            }
        )
        log("custom: optimize complete — compare uses per-market sweep winners", flush=True)

    compare_results: list[dict[str, Any]] = []
    for index, csv_path in enumerate(csv_paths, start=1):
        log(f"custom: compare [{index}/{len(csv_paths)}] {csv_path.name}", flush=True)
        try:
            payload = run_strategy_compare(
                StrategyCompareOptions(
                    csv_path=csv_path,
                    visualize=bool(body.get("visualize", True)),
                    cash=float(body.get("cash") or 10_000.0),
                    fee=float(
                        body.get("fee") if body.get("fee") not in (None, "") else DEFAULT_TRADE_FEE_RATE
                    ),
                    slippage=DEFAULT_SLIPPAGE_RATE,
                    execution=str(body.get("execution") or DEFAULT_BACKTEST_EXECUTION),
                    vectorbt=bool(body.get("vectorbt")),
                    strategy_namespace=strategy_namespace,
                    mode=mode,
                    strategy_ids=strategy_id_set,
                    max_strategies=max_strategies,
                    run_start_unix_seconds=effective_run_start.get(
                        csv_path, body.get("run_start_unix_seconds")
                    ),
                    run_end_unix_seconds=body.get("run_end_unix_seconds"),
                    use_optimized_strategy_params=use_optimized,
                    apply_sweep_winner=apply_sweep_winner,
                ),
                log=log,
            )
        except Exception as exc:
            _log_file_failure(log, "compare", csv_path.name, exc)
            compare_results.append(
                {
                    "csv": str(csv_path),
                    "skipped": True,
                    "failed": True,
                    "reason": str(exc),
                    "error_type": type(exc).__name__,
                }
            )
            continue
        strategies = payload.get("strategies") if isinstance(payload.get("strategies"), list) else []
        buy_and_hold = payload.get("buy_and_hold_return_pct")
        beat_buy_hold = 0
        if isinstance(buy_and_hold, (int, float)):
            for row in strategies:
                if not isinstance(row, dict):
                    continue
                excess = row.get("excess_vs_buy_hold_pct")
                if excess is None:
                    excess = float(row.get("return_pct", 0)) - float(buy_and_hold)
                if float(excess) > 0:
                    beat_buy_hold += 1
        best_return = None
        if strategies and isinstance(strategies[0], dict):
            best_return = strategies[0].get("return_pct")
        compare_results.append(
            {
                "csv": str(csv_path),
                "best_strategy_id": payload.get("best_strategy_id"),
                "best_return_pct": best_return,
                "buy_and_hold_return_pct": buy_and_hold,
                "strategies_count": len(strategies),
                "strategies_beat_buy_hold": beat_buy_hold,
            }
        )
    succeeded = [entry for entry in compare_results if not entry.get("skipped")]
    if not succeeded:
        reasons = "; ".join(str(entry.get("reason", entry.get("csv"))) for entry in compare_results)
        raise ValueError(f"no dataset left bars in the run window: {reasons}")
    summary["compare"] = compare_results
    summary["steps"].append(
        {"step": "compare", "datasets": len(succeeded), "skipped": len(compare_results) - len(succeeded)}
    )

    _log_failure_summary(log, summary)
    log(json.dumps(summary, indent=2), flush=True)
    return summary
