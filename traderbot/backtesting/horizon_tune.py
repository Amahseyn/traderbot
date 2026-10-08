from __future__ import annotations

import json
from pathlib import Path

from traderbot.data.crypto_store import (
    DEFAULT_HORIZON_LABELS,
    HORIZON_MANIFEST,
    default_crypto_root,
)
from traderbot.utils.horizons import horizon_label
from traderbot.utils.resolution import resolution_from_csv_path, resolution_minutes


def dataset_horizon_label_for_csv(csv_path: Path | str) -> str:
    """Wall-clock label of one bar (e.g. ``60`` -> ``1h``, ``15`` -> ``15m``)."""
    resolution = resolution_from_csv_path(Path(csv_path).name)
    return horizon_label(resolution_minutes(resolution), 1)


def filter_csv_paths_for_horizon_tuning(
    csv_paths: list[Path],
    horizon_tune_label: str,
) -> list[Path]:
    """Keep only datasets whose native bar horizon matches the tune bucket label."""
    return sorted(
        path
        for path in csv_paths
        if dataset_horizon_label_for_csv(path) == horizon_tune_label
    )


def list_csv_paths_for_horizon_tuning(
    horizon_tune_label: str,
    *,
    crypto_root: Path | None = None,
    max_samples: int = 100,
) -> list[Path]:
    """Manifest or folder listing, then strict dataset-horizon filter."""
    root = (crypto_root or default_crypto_root()).resolve()
    manifest_path = root / HORIZON_MANIFEST
    candidates: list[Path] = []
    if manifest_path.is_file():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = (data.get("horizons") or {}).get(horizon_tune_label, {}).get("files") or []
        candidates = [root / entry["path"] for entry in files]
        candidates = [path for path in candidates if path.is_file()]
    if not candidates:
        horizon_dir = root / "horizons" / horizon_tune_label
        if horizon_dir.is_dir():
            candidates = sorted(horizon_dir.glob("*.csv"))
    filtered = filter_csv_paths_for_horizon_tuning(candidates, horizon_tune_label)
    return filtered[:max_samples]


def all_horizon_tune_labels(*, crypto_root: Path | None = None) -> list[str]:
    root = (crypto_root or default_crypto_root()).resolve()
    labels = set(DEFAULT_HORIZON_LABELS)
    horizons_dir = root / "horizons"
    if horizons_dir.is_dir():
        labels.update(p.name for p in horizons_dir.iterdir() if p.is_dir())
    return sorted(labels)
