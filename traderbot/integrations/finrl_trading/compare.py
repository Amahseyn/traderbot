"""Compare FinRL-aligned traderbot strategies on exported Hyperliquid CSVs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from traderbot.integrations.finrl_trading.capabilities import (
    FINRL_ENSEMBLE_PRESETS,
    FINRL_HYPERLIQUID_STRATEGY_IDS,
)

LogFn = Callable[[str], None]


def _log_default(msg: str) -> None:
    print(msg, flush=True)


def compare_finrl_strategies_on_csv(
    csv_path: Path,
    *,
    strategy_ids: tuple[str, ...] | None = None,
    exchange: str = "hyperliquid",
    use_optimized_params: bool = True,
    log: LogFn | None = None,
) -> dict[str, Any]:
    from traderbot.algorithms.cli_args import default_strategy_namespace
    from traderbot.algorithms.registry import algorithm_for_id, strategy_kwargs_from_namespace
    from traderbot.algorithms.strategy_defaults import apply_robust_defaults, apply_strategy_baseline_defaults
    from traderbot.algorithms.optimized_params import resolve_optimized_namespace
    from traderbot.backtesting import backtest_summary_dict, load_bars_csv, run_backtest
    from traderbot.data.intrahour import enrich_bars_for_csv
    from traderbot.markets.execution_costs import execution_cost_profile
    from traderbot.utils.resolution import resolution_from_csv_path

    log = log or _log_default
    costs = execution_cost_profile(exchange, fee_role="taker", market_kind="perp")
    resolution = resolution_from_csv_path(csv_path.name)
    bars = enrich_bars_for_csv(load_bars_csv(csv_path), csv_path, default_strategy_namespace())

    ids = strategy_ids or FINRL_HYPERLIQUID_STRATEGY_IDS
    rows: list[dict[str, Any]] = []

    for strategy_id in ids:
        if strategy_id == "ensemble":
            for preset in FINRL_ENSEMBLE_PRESETS:
                ns = default_strategy_namespace(ensemble_preset=preset)
                apply_strategy_baseline_defaults(ns, strategy_id)
                if use_optimized_params:
                    apply_robust_defaults(ns, strategy_id, resolution=resolution)
                    ns = resolve_optimized_namespace(
                        strategy_id, ns, csv_path=csv_path, resolution=resolution
                    )
                kwargs = strategy_kwargs_from_namespace(strategy_id, ns)
                algo = algorithm_for_id(strategy_id, **kwargs)
                result = run_backtest(
                    algo,
                    bars,
                    initial_cash=10_000.0,
                    fee_rate=costs.fee_rate,
                    slippage_rate=costs.slippage_rate,
                    execution="next_open",
                )
                summary = backtest_summary_dict(algo, result, bars=len(bars))
                summary["strategy_id"] = strategy_id
                summary["ensemble_preset"] = preset
                rows.append(summary)
                log(f"compare {csv_path.name} ensemble/{preset}: {summary.get('return_pct')}%")
            continue

        ns = default_strategy_namespace()
        apply_strategy_baseline_defaults(ns, strategy_id)
        if use_optimized_params:
            apply_robust_defaults(ns, strategy_id, resolution=resolution)
            ns = resolve_optimized_namespace(
                strategy_id, ns, csv_path=csv_path, resolution=resolution
            )
        kwargs = strategy_kwargs_from_namespace(strategy_id, ns)
        algo = algorithm_for_id(strategy_id, **kwargs)
        result = run_backtest(
            algo,
            bars,
            initial_cash=10_000.0,
            fee_rate=costs.fee_rate,
            slippage_rate=costs.slippage_rate,
            execution="next_open",
        )
        summary = backtest_summary_dict(algo, result, bars=len(bars))
        summary["strategy_id"] = strategy_id
        rows.append(summary)
        log(f"compare {csv_path.name} {strategy_id}: {summary.get('return_pct')}%")

    ranked = sorted(rows, key=lambda r: float(r.get("return_pct") or -1e9), reverse=True)
    best = ranked[0] if ranked else None
    return {
        "csv": str(csv_path),
        "resolution": resolution,
        "exchange": exchange,
        "use_optimized_params": use_optimized_params,
        "results": rows,
        "best": best,
    }
