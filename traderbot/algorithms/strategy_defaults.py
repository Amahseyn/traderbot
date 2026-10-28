from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULTS_PATH = Path(__file__).with_name("strategy_defaults.json")

#: Strategies whose entries follow a cross/trend rather than fading an extreme.
TREND_STRATEGIES = ("sma_cross", "ema_cross", "macd_cross")

#: The shared ``--buy-min-recent-return`` / ``--sell-max-recent-return`` defaults, which are
#: mean-reversion semantics; trend strategies replace them with 0.0 / 0.0.
GENERIC_BUY_MIN_RECENT_RETURN = -0.03
GENERIC_SELL_MAX_RECENT_RETURN = 0.03

#: Bars this short are where the roundtrip friction (0.19% on Hyperliquid taker) rivals or
#: exceeds the median candle, so the cost-aware edge gate is on by default at or below it.
#: Coarser bars clear the friction on their own; there the gate only costs trades.
HIGH_FREQUENCY_MAX_BAR_MINUTES = 5

#: Default ``min_edge_over_cost`` for high-frequency bars: break-even (1x the roundtrip cost).
HIGH_FREQUENCY_MIN_EDGE_OVER_COST = 1.0


def defaults_path() -> Path:
    return DEFAULTS_PATH


def load_robust_defaults_file(path: Path | str | None = None) -> dict[str, Any]:
    """Load the tuned-defaults file (empty dict when it does not exist yet)."""
    defaults_file = Path(path) if path is not None else DEFAULTS_PATH
    if not defaults_file.exists():
        return {}
    return json.loads(defaults_file.read_text(encoding="utf-8"))


def _bucket_keys(*, resolution: str | None, horizon_label: str | None) -> list[str]:
    keys: list[str] = []
    if horizon_label:
        keys.append(f"horizon:{horizon_label}")
    if resolution:
        keys.append(f"resolution:{resolution}")
    keys.append("resolution:any")
    return keys


def horizon_bucket_label_for_csv(csv_path: Path | str | None) -> str | None:
    """Horizon folder label for defaults buckets, only when it names the dataset's bar size."""
    if csv_path is None:
        return None
    from traderbot.backtesting.horizon_tune import dataset_horizon_label_for_csv
    from traderbot.data.crypto_store import horizon_label_from_csv_dir

    csv = Path(csv_path)
    label = horizon_label_from_csv_dir(csv.parent)
    if label is None:
        return None
    return label if dataset_horizon_label_for_csv(csv) == label else None


def robust_params_for(
    strategy_id: str,
    *,
    resolution: str | None = None,
    horizon_label: str | None = None,
    path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Averaged robust defaults for one strategy (None when never tuned)."""
    content = load_robust_defaults_file(path)
    for key in _bucket_keys(resolution=resolution, horizon_label=horizon_label):
        entry = (content.get(key) or {}).get(strategy_id)
        if entry and entry.get("robust_params"):
            return dict(entry["robust_params"])
    return None


def best_params_for(
    strategy_id: str,
    *,
    resolution: str | None = None,
    horizon_label: str | None = None,
    path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Single-run winner for one strategy (kept separate from robust defaults)."""
    content = load_robust_defaults_file(path)
    for key in _bucket_keys(resolution=resolution, horizon_label=horizon_label):
        entry = (content.get(key) or {}).get(strategy_id)
        if entry and entry.get("best_params"):
            return dict(entry["best_params"])
    return None


def apply_strategy_baseline_defaults(namespace: Any, strategy_id: str) -> list[str]:
    """Map shared CLI defaults (5/20 MA, period 14) to each strategy's class defaults."""
    applied: list[str] = []
    generic_ma = getattr(namespace, "fast", None) == 5 and getattr(namespace, "slow", None) == 20
    if strategy_id in ("ema_cross", "macd_cross") and generic_ma:
        namespace.fast = 12
        namespace.slow = 26
        applied.extend(["fast", "slow"])
    if strategy_id == "finrl_ema_intraday" and generic_ma:
        namespace.fast = 12
        namespace.slow = 48
        applied.extend(["fast", "slow"])
    if strategy_id == "bollinger_mean_reversion" and getattr(namespace, "period", None) == 14:
        namespace.period = 20
        applied.append("period")
    if strategy_id in TREND_STRATEGIES and _has_generic_mean_reversion_bounds(namespace):
        # Mean reversion skips buys into a -3% dump; a trend entry wants the opposite sign, so
        # the shared bounds become "the recent path must already point the way we trade".
        namespace.buy_min_recent_return = 0.0
        namespace.sell_max_recent_return = 0.0
        applied.extend(["buy_min_recent_return", "sell_max_recent_return"])
    return applied


def _has_generic_mean_reversion_bounds(namespace: Any) -> bool:
    return (
        getattr(namespace, "buy_min_recent_return", None) == GENERIC_BUY_MIN_RECENT_RETURN
        and getattr(namespace, "sell_max_recent_return", None) == GENERIC_SELL_MAX_RECENT_RETURN
    )


def apply_venue_cost_default(namespace: Any, csv_path: Path | str | None) -> list[str]:
    """Fill ``roundtrip_cost_pct`` from the CSV venue so the cost gate scales by exchange.

    An explicit value (including ``0`` to disable the gate) always wins; ``None`` means the
    caller never set it.
    """
    if getattr(namespace, "roundtrip_cost_pct", None) is not None:
        return []
    from traderbot.utils.trading_costs import roundtrip_cost_pct

    maker_entry = str(getattr(namespace, "entry_order_mode", "market")) == "maker"
    namespace.roundtrip_cost_pct = roundtrip_cost_pct(source=csv_path, maker_entry=maker_entry)
    return ["roundtrip_cost_pct"]


def apply_high_frequency_edge_default(namespace: Any, bar_minutes: int | None) -> list[str]:
    """Resolve ``min_edge_over_cost=None`` to the break-even gate on 1m–5m bars only.

    Coarser bars already clear the roundtrip friction, so the gate there only removes trades
    (measured: 60m ``macd_cross`` on ARBUSDT went from -1.8% to -22.3% when forced on).
    """
    if getattr(namespace, "min_edge_over_cost", None) is not None:
        return []
    high_frequency = bar_minutes is not None and bar_minutes <= HIGH_FREQUENCY_MAX_BAR_MINUTES
    namespace.min_edge_over_cost = HIGH_FREQUENCY_MIN_EDGE_OVER_COST if high_frequency else 0.0
    return ["min_edge_over_cost"]


def apply_robust_defaults(
    namespace: Any,
    strategy_id: str,
    *,
    resolution: str | None = None,
    horizon_label: str | None = None,
    path: Path | str | None = None,
) -> list[str]:
    """Copy tuned robust params onto a strategy namespace; returns applied names.

    Falls back to the code defaults in ``default_strategy_namespace`` for any
    knob the file does not cover, so stock behavior never breaks.
    """
    params = robust_params_for(strategy_id, resolution=resolution, horizon_label=horizon_label, path=path)
    if not params:
        return []
    applied: list[str] = []
    for name, value in params.items():
        if hasattr(namespace, name):
            setattr(namespace, name, value)
            applied.append(name)
    return applied


def namespace_for_strategy_backtest(
    strategy_id: str,
    base: Any | None = None,
    *,
    csv_path: Path | str | None = None,
    defaults_file: Path | str | None = None,
    resolution: str | None = None,
) -> Any:
    """Merge CLI/Lab namespace defaults with tuned params for this strategy and data path."""
    from traderbot.algorithms.cli_args import merge_strategy_namespace
    from traderbot.utils.resolution import resolution_from_csv_path, resolution_minutes

    namespace = merge_strategy_namespace(base)
    apply_strategy_baseline_defaults(namespace, strategy_id)
    csv = Path(csv_path) if csv_path is not None else None
    apply_venue_cost_default(namespace, csv)
    horizon_label = horizon_bucket_label_for_csv(csv)
    resolved_resolution: str | None = str(resolution) if resolution is not None else None
    if csv is not None:
        try:
            resolved_resolution = resolution_from_csv_path(csv.name)
        except (ValueError, IndexError):
            pass
    bar_minutes: int | None = None
    if resolved_resolution is not None:
        try:
            bar_minutes = resolution_minutes(resolved_resolution)
        except ValueError:
            bar_minutes = None
    apply_high_frequency_edge_default(namespace, bar_minutes)
    apply_robust_defaults(
        namespace,
        strategy_id,
        resolution=resolved_resolution,
        horizon_label=horizon_label,
        path=defaults_file,
    )
    return namespace
