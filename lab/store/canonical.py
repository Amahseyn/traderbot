from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from traderbot.algorithms.base import Algorithm


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def content_hash_for_configuration(
    *,
    config_kind: str,
    strategy_id: str | None,
    model_id: str | None,
    symbol: str | None,
    resolution: str | None,
    horizon_label: str | None,
    parameters: dict[str, Any],
    data_context: dict[str, Any],
) -> str:
    body = {
        "config_kind": config_kind,
        "strategy_id": strategy_id,
        "model_id": model_id,
        "symbol": symbol,
        "resolution": resolution,
        "horizon_label": horizon_label,
        "parameters": parameters,
        "data_context": data_context,
    }
    digest = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
    return digest[:32]


_SYMBOL_RESOLUTION_RE = re.compile(r"^([A-Z0-9]+)_(.+)$", re.IGNORECASE)


def parse_symbol_resolution_from_csv(csv_path: Path | str | None) -> tuple[str | None, str | None]:
    if not csv_path:
        return None, None
    stem = Path(csv_path).stem
    match = _SYMBOL_RESOLUTION_RE.match(stem)
    if not match:
        return None, None
    return match.group(1).upper(), match.group(2)


def build_strategy_parameters(algorithm: Algorithm) -> dict[str, Any]:
    parameters: dict[str, Any] = {"algorithm": algorithm.name}
    for key, value in vars(algorithm).items():
        if key.startswith("_"):
            continue
        parameters[key] = value
    return parameters
