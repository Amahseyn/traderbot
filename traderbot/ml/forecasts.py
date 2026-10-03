from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol


class _ForecastRun(Protocol):
    model_id: str
    horizon_label: str
    horizon_bars: int
    timestamps: list[int]
    y_pred: list[float]


def build_forecast_by_timestamp(result: _ForecastRun) -> dict[int, float]:
    return dict(zip(result.timestamps, result.y_pred, strict=True))


def write_holdout_forecasts(result: _ForecastRun, path: Path) -> Path:
    payload: dict[str, Any] = {
        "model_id": result.model_id,
        "horizon_label": result.horizon_label,
        "horizon_bars": result.horizon_bars,
        "forecasts": [
            {"timestamp": int(timestamp), "predicted_log_return": float(pred)}
            for timestamp, pred in zip(result.timestamps, result.y_pred, strict=True)
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_forecast_by_timestamp(path: Path) -> dict[int, float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("forecasts")
    if not isinstance(rows, list):
        raise ValueError(f"invalid forecast file (missing forecasts list): {path}")
    out: dict[int, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        timestamp = int(row["timestamp"])
        out[timestamp] = float(row["predicted_log_return"])
    return out
