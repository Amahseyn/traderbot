from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from traderbot.algorithms.registry import algorithm_for_id
from traderbot.backtesting import backtest_summary_dict, run_backtest, save_backtest_result


_FORECAST_COMPARE_SPECS: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("forecast_signal", "forecast_signal", {}),
    (
        "ml_gated",
        "ml_gated",
        {"gate_mode": "forecast_filters_rule", "base_strategy_id": "rsi_threshold"},
    ),
    (
        "ml_gated_rule_filters",
        "ml_gated",
        {"gate_mode": "rule_filters_forecast", "base_strategy_id": "rsi_threshold"},
    ),
)


def append_forecast_strategy_compare_rows(
    *,
    bars: list[dict[str, Any]],
    forecast_by_timestamp: Mapping[int, float],
    initial_cash: float,
    ranked: list[dict[str, Any]],
    equity_by_strategy: dict[str, list[tuple[int, float]]],
    tree,
    slice_csv: Path,
) -> None:
    """Backtest ML forecast strategies and merge into an existing compare manifest payload."""
    for manifest_strategy_id, algorithm_id, extra in _FORECAST_COMPARE_SPECS:
        algo = algorithm_for_id(
            algorithm_id,
            forecast_by_timestamp=forecast_by_timestamp,
            **extra,
        )
        backtest_result = run_backtest(algo, bars, initial_cash=initial_cash, fee_rate=0.0)
        equity_by_strategy[manifest_strategy_id] = list(backtest_result.equity_curve)
        ranked.append(
            backtest_summary_dict(
                algo,
                backtest_result,
                bars=len(bars),
                extra={"strategy_id": manifest_strategy_id, "algorithm_id": algorithm_id, **extra},
            )
        )
        run_dir = tree.run_dir_flat(manifest_strategy_id)
        save_backtest_result(
            algo,
            backtest_result,
            run_dir,
            bars=len(bars),
            bar_rows=bars,
            visualize=True,
            extra={"strategy_id": manifest_strategy_id, "csv": str(slice_csv), **extra},
        )
