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
