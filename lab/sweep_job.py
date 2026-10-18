from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from traderbot.backtesting.robust_defaults import tune_grid_for_strategy
from traderbot.backtesting.optimize_select import optimize_config_from_body, run_strategy_optimize
from traderbot.backtesting.sweep import SweepOptions
from traderbot.utils.trading_costs import (
    DEFAULT_BACKTEST_EXECUTION,
    DEFAULT_SLIPPAGE_RATE,
    DEFAULT_TRADE_FEE_RATE,
)


def param_grid_from_job_body(body: dict[str, Any], strategy_id: str) -> dict[str, list[Any]]:
    raw = body.get("param_grid")
    if isinstance(raw, dict) and raw:
        return {name: list(values) for name, values in raw.items()}
    per_strategy = body.get("param_grids_by_strategy")
    if isinstance(per_strategy, dict):
        grid = per_strategy.get(strategy_id)
        if isinstance(grid, dict) and grid:
            return {name: list(values) for name, values in grid.items()}
    return tune_grid_for_strategy(strategy_id, full=bool(body.get("full_grid")))


def run_recorded_strategy_sweep(
    body: dict[str, Any],
    csv_path: Path,
    *,
    bars: list[dict[str, Any]] | None = None,
    log: Any = print,
) -> dict[str, Any]:
    """Run a grid sweep and persist the manifest + SQLite sweep session (when Lab DB is available)."""
    from lab.tasks import _strategy_namespace_from_body

    csv = Path(csv_path)
    strategy_id = str(body.get("strategy_id") or "")
    param_grid = param_grid_from_job_body(body, strategy_id)
    holdout_raw = body.get("holdout_tail_bars")
    if holdout_raw in (None, "") and body.get("optimize_holdout_tail_bars") not in (None, ""):
        holdout_raw = body.get("optimize_holdout_tail_bars")
    min_trades_raw = body.get("min_trades")
    if min_trades_raw in (None, "") and body.get("optimize_min_trades") not in (None, ""):
        min_trades_raw = body.get("optimize_min_trades")
    max_combos_raw = body.get("max_combos")
    if max_combos_raw in (None, "") and body.get("optimize_max_combos") not in (None, ""):
        max_combos_raw = body.get("optimize_max_combos")
    method = str(body.get("optimize_method") or body.get("optimizer_method") or "grid")
    if method == "optuna":
        trials = body.get("optimize_n_trials", body.get("n_trials", 80))
        log(f"sweep optuna: {strategy_id} on {csv.name} (n_trials={trials})", flush=True)
    else:
        log(f"sweep grid: {strategy_id} on {csv.name} ({len(param_grid)} params)", flush=True)
    from traderbot.backtesting.bar_windows import compare_window_utc_from_unix

    optimize_config = optimize_config_from_body(body)
    payload = run_strategy_optimize(
        SweepOptions(
            csv_path=csv,
            strategy_id=strategy_id,
            param_grid=param_grid,
            bars=bars,
            cash=float(body.get("cash") or 10_000.0),
            fee=float(body.get("fee") if body.get("fee") not in (None, "") else DEFAULT_TRADE_FEE_RATE),
            slippage=DEFAULT_SLIPPAGE_RATE,
            execution=str(body.get("execution") or DEFAULT_BACKTEST_EXECUTION),
            holdout_tail_bars=None if holdout_raw in (None, "") else int(holdout_raw),
            min_trades=int(min_trades_raw or 0),
            max_combos=int(max_combos_raw or 64),
        ),
        _strategy_namespace_from_body(body),
        config=optimize_config,
    )
    def _unix_opt(raw: Any) -> int | None:
        if raw in (None, ""):
            return None
        return int(raw)

    compare_start, compare_end = compare_window_utc_from_unix(
        _unix_opt(body.get("run_start_unix_seconds")),
        _unix_opt(body.get("run_end_unix_seconds")),
    )
    if compare_start is not None:
        payload["compare_start_utc"] = compare_start
        payload["compare_end_utc"] = compare_end
    out = body.get("out")
    out_dir = Path(str(out)) if out else Path("results") / "strategies" / "sweep" / f"{csv.stem}_{strategy_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "sweep_manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["manifest"] = str(manifest_path)
    import lab.store  # noqa: F401 — registers try_record hook for sweep_sessions

    from traderbot.recording import try_record

    try_record("sweep_session", sweep_payload=payload, manifest_path=manifest_path)
    return payload
