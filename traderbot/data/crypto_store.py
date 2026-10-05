from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from traderbot.data.export import write_csv
from traderbot.utils.horizons import (
    DEFAULT_HORIZONS,
    horizons_for_resolution,
    min_bars_for_eval,
)
from traderbot.utils.resolution import resolution_from_csv_path, resolution_minutes

CRYPTO_DATA_ROOT = Path("data/crypto")
OHLC_SUBDIR = "ohlc"
HORIZONS_SUBDIR = "horizons"
HORIZON_MANIFEST = "horizon_manifest.json"

DEFAULT_HORIZON_LABELS: frozenset[str] = frozenset(label for _, label in DEFAULT_HORIZONS)


def default_crypto_root() -> Path:
    return CRYPTO_DATA_ROOT


def crypto_ohlc_dir(crypto_root: Path | None = None) -> Path:
    root = crypto_root or default_crypto_root()
    return root / OHLC_SUBDIR


def resolve_crypto_data_dir(path: Path | None = None) -> Path | None:
    """
    Prefer ``data/crypto/ohlc``, then legacy ``data/multisource``.

    Returns ``None`` when no exported CSV tree exists.
    """
    if path is not None:
        resolved = path.resolve()
        if resolved.is_dir() and list(resolved.glob("*.csv")):
            return resolved
        ohlc = resolved / OHLC_SUBDIR
        if ohlc.is_dir() and list(ohlc.glob("*.csv")):
            return ohlc
        return resolved if resolved.is_dir() else None

    for candidate in (crypto_ohlc_dir(), Path("data/multisource")):
        if candidate.is_dir() and list(candidate.glob("*.csv")):
            return candidate.resolve()
    return None




ONE_HOUR_OHLC_SUFFIX = "_60.csv"


def crypto_one_hour_csv_for_symbol(symbol: str, ohlc_dir: Path | None = None) -> Path:
    """Path to ``{SYMBOL}_60.csv`` under crypto OHLC (or legacy multisource)."""
    sym = symbol.upper()
    base = ohlc_dir or resolve_crypto_data_dir() or crypto_ohlc_dir()
    return base / f"{sym}{ONE_HOUR_OHLC_SUFFIX}"


def list_crypto_one_hour_csvs(ohlc_dir: Path | None = None) -> list[Path]:
    """Every on-disk 1h OHLC CSV (``*_60.csv``), sorted by name."""
    base = ohlc_dir or resolve_crypto_data_dir()
    if base is None or not base.is_dir():
        return []
    return sorted(base.glob(f"*{ONE_HOUR_OHLC_SUFFIX}"))


def resolve_crypto_1h_csv_paths(
    *,
    csv_path: Path | None = None,
    symbol: str | None = None,
    all_assets: bool = False,
) -> list[Path]:
    """
    Resolve 1h OHLC inputs for local pipelines.

    ``all_assets`` → every ``*_60.csv``; else ``csv_path``, else ``symbol``, else BTCIRT default.
    """
    if all_assets:
        paths = list_crypto_one_hour_csvs()
        if not paths:
            raise FileNotFoundError("no *_60.csv under data/crypto/ohlc; export first")
        return paths
    if csv_path is not None:
        return [csv_path]
    if symbol is not None:
        path = crypto_one_hour_csv_for_symbol(symbol)
        return [path]
    return [crypto_one_hour_csv_for_symbol("BTCIRT")]

def is_default_horizon_label(label: str) -> bool:
    return label in DEFAULT_HORIZON_LABELS


def horizon_label_from_csv_dir(csv_dir: Path) -> str | None:
    """If ``csv_dir`` is ``.../horizons/<label>/``, return ``<label>``."""
    parts = csv_dir.resolve().parts
    if HORIZONS_SUBDIR not in parts:
        return None
    idx = parts.index(HORIZONS_SUBDIR)
    if idx + 1 >= len(parts):
        return None
    label = parts[idx + 1]
    return label if is_default_horizon_label(label) else None


def recommended_tail_bars(horizon_bars: int, *, train_ratio = 0.8) -> int:
    """Raw OHLC rows to keep (from the end) for a purge-safe eval holdout."""
    return min_bars_for_eval(horizon_bars, train_ratio=train_ratio)


def _expected_step_seconds(resolution: str) -> int:
    return resolution_minutes(resolution) * 60


def is_contiguous_tail(rows: list[dict[str, Any]], resolution: str) -> bool:
    """True when timestamps advance by exactly one candle step (no gaps)."""
    if len(rows) < 2:
        return len(rows) >= 1
    step = _expected_step_seconds(resolution)
    for prev, cur in zip(rows, rows[1:], strict=False):
        delta = int(cur["timestamp"]) - int(prev["timestamp"])
        if delta != step:
            return False
    return True


def trim_tail_rows(rows: list[dict[str, Any]], tail_bars: int) -> list[dict[str, Any]]:
    if tail_bars <= 0 or len(rows) <= tail_bars:
        return list(rows)
    return list(rows[-tail_bars:])


def build_horizon_datasets(
    ohlc_dir: Path,
    crypto_root: Path | None = None,
    *,
    train_ratio = 0.8,
    tail_bars: int | None = None,
) -> dict[str, Any]:
    """
    Write ``horizons/<label>/<SYMBOL>_<resolution>.csv`` for each default horizon window.

    Each file is the **last** ``tail_bars`` candles from OHLC export, trimmed only when
    the series is contiguous and long enough for that horizon.
    """
    ohlc_dir = ohlc_dir.resolve()
    root = (crypto_root or ohlc_dir.parent).resolve()
    horizons_root = root / HORIZONS_SUBDIR
    horizons_root.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "ohlc_dir": str(ohlc_dir),
        "horizons_dir": str(horizons_root),
        "train_ratio": train_ratio,
        "horizons": {},
    }

    for label in sorted(DEFAULT_HORIZON_LABELS):
        (horizons_root / label).mkdir(parents=True, exist_ok=True)

    for csv_path in sorted(ohlc_dir.glob("*.csv")):
        from traderbot.backtesting import load_bars_csv

        bars = load_bars_csv(csv_path)
        resolution = resolution_from_csv_path(csv_path.name)
        for horizon_bars, label in horizons_for_resolution(resolution):
            need = recommended_tail_bars(horizon_bars, train_ratio=train_ratio)
            use_tail = tail_bars if tail_bars is not None else need
            use_tail = max(use_tail, need)
            if len(bars) < use_tail:
                continue
            slice_rows = trim_tail_rows(bars, use_tail)
            if len(slice_rows) < need:
                continue
            if not is_contiguous_tail(slice_rows, resolution):
                continue
            out_path = horizons_root / label / csv_path.name
            write_csv(out_path, slice_rows)
            entry = manifest["horizons"].setdefault(label, {"files": [], "complete": True})
            entry["files"].append(
                {
                    "path": str(out_path.relative_to(root)),
                    "rows": len(slice_rows),
                    "horizon_bars": horizon_bars,
                    "resolution": resolution,
                    "tail_bars": use_tail,
                }
            )

    for label in sorted(DEFAULT_HORIZON_LABELS):
        label_dir = horizons_root / label
        for stale in label_dir.glob("*.csv"):
            rel = str(stale.relative_to(root))
            listed = {f["path"] for f in manifest["horizons"].get(label, {}).get("files", [])}
            if rel not in listed:
                stale.unlink()

    manifest_path = root / HORIZON_MANIFEST
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def materialize_crypto_tree(
    jobs_written_dir: Path,
    *,
    crypto_root: Path | None = None,
    train_ratio = 0.8,
) -> Path:
    """
    Normalize export output under ``data/crypto``.

    If ``jobs_written_dir`` is already ``.../ohlc``, horizons are built beside it.
    If it is a flat legacy folder, CSVs are copied into ``ohlc/`` first.
    """
    jobs_written_dir = jobs_written_dir.resolve()
    root = (crypto_root or jobs_written_dir.parent).resolve()
    if jobs_written_dir.name != OHLC_SUBDIR and list(jobs_written_dir.glob("*.csv")):
        root = (crypto_root or default_crypto_root()).resolve()

    ohlc = root / OHLC_SUBDIR
    ohlc.mkdir(parents=True, exist_ok=True)

    if jobs_written_dir.resolve() == ohlc.resolve():
        source = ohlc
    elif jobs_written_dir.name == OHLC_SUBDIR and jobs_written_dir.parent.resolve() == root:
        source = jobs_written_dir
    elif list(jobs_written_dir.glob("*.csv")):
        for csv_path in jobs_written_dir.glob("*.csv"):
            shutil.copy2(csv_path, ohlc / csv_path.name)
        export_manifest = jobs_written_dir / "export_manifest.json"
        if export_manifest.is_file():
            shutil.copy2(export_manifest, root / "export_manifest.json")
        source = ohlc
    else:
        source = ohlc

    build_horizon_datasets(source, root, train_ratio=train_ratio)
    return root
