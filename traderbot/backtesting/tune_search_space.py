from __future__ import annotations

from typing import Any

from traderbot.algorithms.cli_args import default_strategy_namespace
from traderbot.algorithms.registry import strategy_param_names
from traderbot.backtesting.robust_defaults import FULL_TUNE_GRIDS

OPTIONAL_FLOAT_CHOICES: tuple[float | None, ...] = (None, -0.08, -0.05, -0.03, -0.02, 0.0)
CATEGORICAL_STRING_PARAMS: dict[str, tuple[str, ...]] = {
    "signal_style": ("level_lag", "cross"),
    "ensemble_entry_rule": ("all", "majority", "primary"),
    "ensemble_exit_rule": ("any", "all", "primary"),
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
    if name == "max_tranches":
        return 1, 3
    if default <= 1:
        return 1, max(3, default + 10)
    low = max(1, default // 3)
    high = max(default * 3, default + 5)
    if "period" in name or "bars" in name or "horizon" in name or "levels" in name or "count" in name:
        high = min(high, 250)
    if name == "lookback_bars":
        low = max(10, low)
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
    """Suggest parameters for one Optuna trial.

    All parameters are sampled from their full, invariant distribution.  Optuna
    requires the choice set of ``suggest_categorical`` to be the same across every
    trial in a study, so we never filter the grid based on another parameter's
    sampled value (the ``fast < slow`` constraint is enforced post-hoc and
    violations raise ``TrialPruned`` upstream).
    """
    from traderbot.algorithms.registry import strategy_param_defaults

    defaults = strategy_param_defaults(strategy_id)
    hints = grid_hints_for_strategy(strategy_id, full=full_grid_hints)
    params: dict[str, Any] = {}
    for name in param_names:
        grid_values = hints.get(name)
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
    if "target_exposure" in params and "max_tranches" in params:
        max_t = int(params["max_tranches"])
        if max_t > 1 and float(params["target_exposure"]) * max_t > 1.0:
            params["target_exposure"] = round(1.0 / max_t, 4)
    if "buy_min_recent_return" in params and "sell_max_recent_return" in params:
        b_ret, s_ret = float(params["buy_min_recent_return"]), float(params["sell_max_recent_return"])
        if b_ret > s_ret:
            params["buy_min_recent_return"], params["sell_max_recent_return"] = s_ret, b_ret
    if "oversold" in params and "overbought" in params:
        o_val, b_val = float(params["oversold"]), float(params["overbought"])
        if o_val >= b_val:
            params["oversold"], params["overbought"] = min(o_val, b_val), max(o_val, b_val)
            if params["oversold"] == params["overbought"]:
                params["oversold"] = max(1.0, params["oversold"] - 1.0)
    if "rsi_trend_exit" in params and "rsi_trend_entry" in params:
        ex_val, en_val = float(params["rsi_trend_exit"]), float(params["rsi_trend_entry"])
        if ex_val >= en_val:
            params["rsi_trend_exit"], params["rsi_trend_entry"] = min(ex_val, en_val), max(ex_val, en_val)
            if params["rsi_trend_exit"] == params["rsi_trend_entry"]:
                params["rsi_trend_exit"] = max(1.0, params["rsi_trend_exit"] - 1.0)
    if "grid_start_price" in params and "grid_end_price" in params:
        p1_val, p2_val = float(params["grid_start_price"]), float(params["grid_end_price"])
        if p1_val >= p2_val:
            params["grid_start_price"], params["grid_end_price"] = min(p1_val, p2_val), max(p1_val, p2_val)
            if params["grid_start_price"] == params["grid_end_price"]:
                params["grid_start_price"] = max(0.01, params["grid_start_price"] * 0.99)
    if "lookback_bars" in params:
        params["lookback_bars"] = max(10, int(params["lookback_bars"]))
    return params


def initial_trial_params(
    strategy_id: str,
    param_names: list[str],
    *,
    full_grid_hints: bool = True,
) -> dict[str, Any]:
    """Known-good parameter candidate (typically strategy defaults) to seed study as Trial 0."""
    from traderbot.algorithms.registry import strategy_param_defaults
    from traderbot.backtesting.param_bounds import float_bounds

    defaults = strategy_param_defaults(strategy_id)
    hints = grid_hints_for_strategy(strategy_id, full=full_grid_hints)
    params: dict[str, Any] = {}
    for name in param_names:
        grid_values = hints.get(name)
        default = defaults.get(name)
        if grid_values:
            params[name] = default if default in grid_values else grid_values[0]
        elif isinstance(default, bool):
            params[name] = default
        elif isinstance(default, int):
            low, high = _int_bounds(name, default)
            params[name] = max(low, min(high, default))
        elif isinstance(default, float):
            low, high = float_bounds(name, default)
            params[name] = max(low, min(high, default)) if low < high else default
        elif isinstance(default, str):
            choices = CATEGORICAL_STRING_PARAMS.get(name)
            if choices and default not in choices:
                params[name] = choices[0]
            else:
                params[name] = default
        elif default is None:
            params[name] = None
    return params
