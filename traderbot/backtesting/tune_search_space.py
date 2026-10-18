from __future__ import annotations

from typing import Any

from traderbot.algorithms.cli_args import default_strategy_namespace
from traderbot.algorithms.registry import strategy_param_names
from traderbot.backtesting.robust_defaults import FULL_TUNE_GRIDS

OPTIONAL_FLOAT_CHOICES: tuple[float | None, ...] = (None, -0.08, -0.05, -0.03, -0.02, 0.0)
CATEGORICAL_STRING_PARAMS: dict[str, tuple[str, ...]] = {
    "signal_style": ("level_lag", "cross"),
    "ensemble_entry_rule": ("all", "majority", "primary"),
    "ensemble_exit_rule": ("all", "majority", "primary"),
    "ma_kind": ("sma", "ema"),
    "ma_entry_mode": ("golden_cross", "price_cross"),
    "execution": ("close", "next_open"),
}


def resolve_tune_param_names(
    strategy_id: str,
    *,
    search_params: list[str] | None = None,
) -> list[str]:
    allowed = set(strategy_param_names(strategy_id))
    if not search_params:
        return list(allowed)
    names: list[str] = []
    for raw in search_params:
        name = str(raw).strip()
        if name and name in allowed and name not in names:
            names.append(name)
    if not names:
        raise ValueError(f"no valid search_params for strategy {strategy_id!r}")
    return names


def grid_hints_for_strategy(strategy_id: str, *, full: bool = True) -> dict[str, list[Any]]:
    if not full:
        from traderbot.backtesting.robust_defaults import DEFAULT_TUNE_GRIDS

        source = DEFAULT_TUNE_GRIDS
    else:
        source = FULL_TUNE_GRIDS
    grid = source.get(strategy_id)
    if not grid:
        return {}
    return {name: list(values) for name, values in grid.items()}


def _int_bounds(name: str, default: int) -> tuple[int, int]:
    if default <= 1:
        return 1, max(3, default + 10)
    low = max(1, default // 3)
    high = max(default * 3, default + 5)
    if "period" in name or "bars" in name or "horizon" in name or "levels" in name or "count" in name:
        high = min(high, 250)
    if name in ("fast", "trend_fast_period"):
        high = min(high, 80)
    if name in ("slow", "trend_slow_period", "signal"):
        high = min(high, 300)
    return low, high


def suggest_strategy_param(
    trial: Any,
    name: str,
    *,
    default: Any,
    grid_values: list[Any] | None,
) -> Any:
    """Map one namespace field to an Optuna suggestion."""
    if grid_values:
        from traderbot.backtesting.param_bounds import param_value_error

        unique: list[Any] = []
        for value in grid_values:
            if value not in unique and param_value_error(name, value) is None:
                unique.append(value)
        if unique:
            return trial.suggest_categorical(name, unique)

    if isinstance(default, bool):
        return trial.suggest_categorical(name, [False, True])
    if isinstance(default, int):
        low, high = _int_bounds(name, default)
        return trial.suggest_int(name, low, high)
    if isinstance(default, float):
        from traderbot.backtesting.param_bounds import float_bounds

        low, high = float_bounds(name, default)
        if low >= high:
            return default
        return trial.suggest_float(name, low, high)
    if default is None:
        return trial.suggest_categorical(name, list(OPTIONAL_FLOAT_CHOICES))
    if isinstance(default, str):
        choices = CATEGORICAL_STRING_PARAMS.get(name)
        if choices:
            return trial.suggest_categorical(name, list(choices))
        return default
    return default


def suggest_strategy_params(
    trial: Any,
    strategy_id: str,
    param_names: list[str],
    *,
    full_grid_hints: bool = True,
) -> dict[str, Any]:
    from traderbot.algorithms.registry import strategy_param_defaults

    defaults = strategy_param_defaults(strategy_id)
    hints = grid_hints_for_strategy(strategy_id, full=full_grid_hints)
    params: dict[str, Any] = {}
    for name in param_names:
        grid_values = hints.get(name)
        if name == "slow" and "fast" in params and grid_values:
            slow_choices = [value for value in grid_values if int(value) > int(params["fast"])]
            if not slow_choices:
                raise ValueError("no slow choices greater than fast")
            params[name] = trial.suggest_categorical(name, slow_choices)
            continue
        if name == "trend_slow_period" and "trend_fast_period" in params and grid_values:
            slow_choices = [
                value for value in grid_values if int(value) > int(params["trend_fast_period"])
            ]
            if not slow_choices:
                raise ValueError("no trend_slow_period choices greater than trend_fast_period")
            params[name] = trial.suggest_categorical(name, slow_choices)
            continue
        params[name] = suggest_strategy_param(
            trial,
            name,
            default=defaults.get(name),
            grid_values=grid_values,
        )
    fast_key = "fast" if "fast" in params else None
    slow_key = "slow" if "slow" in params else None
    if fast_key and slow_key and int(params[fast_key]) >= int(params[slow_key]):
        raise ValueError("fast must be < slow")
    if "trend_fast_period" in params and "trend_slow_period" in params:
        if int(params["trend_fast_period"]) >= int(params["trend_slow_period"]):
            raise ValueError("trend_fast_period must be < trend_slow_period")
    return params
