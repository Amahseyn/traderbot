from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULTS_PATH = Path(__file__).with_name("strategy_defaults.json")

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
    if strategy_id == "bollinger_mean_reversion" and getattr(namespace, "period", None) == 14:
        namespace.period = 20
        applied.append("period")
    return applied


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
    from traderbot.data.crypto_store import horizon_label_from_csv_dir
    from traderbot.utils.resolution import resolution_from_csv_path

    from traderbot.backtesting.horizon_tune import dataset_horizon_label_for_csv

    namespace = merge_strategy_namespace(base)
    apply_strategy_baseline_defaults(namespace, strategy_id)
    csv = Path(csv_path) if csv_path is not None else None
    horizon_label = horizon_label_from_csv_dir(csv.parent) if csv is not None else None
    if horizon_label and csv is not None:
        if dataset_horizon_label_for_csv(csv) != horizon_label:
            horizon_label = None
    resolved_resolution: str | None = str(resolution) if resolution is not None else None
    if csv is not None:
        try:
            resolved_resolution = resolution_from_csv_path(csv.name)
        except (ValueError, IndexError):
            pass
    apply_robust_defaults(
        namespace,
        strategy_id,
        resolution=resolved_resolution,
        horizon_label=horizon_label,
        path=defaults_file,
    )
    return namespace
