from __future__ import annotations

import sqlite3
from pathlib import Path

from traderbot.pipelines.experiment_config import (
    DEFAULT_EXPERIMENT_CONFIG_DIR,
    REPO_ROOT,
    experiment_config_to_dict,
    load_experiment_config,
)
from lab.store.record import upsert_experiment

_SKIP_CONFIG_NAMES = frozenset({"experiment.example.json"})


def _repo_relative_config_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(resolved)


def sync_experiment_config_files(
    connection: sqlite3.Connection,
    *,
    config_dir: Path | None = None,
) -> int:
    """Register ``config/experiment*.json`` files in the experiments catalog (no pipeline run)."""
    root = (config_dir or DEFAULT_EXPERIMENT_CONFIG_DIR).resolve()
    if not root.is_dir():
        return 0
    registered = 0
    for path in sorted(root.glob("experiment*.json")):
        if path.name in _SKIP_CONFIG_NAMES:
            continue
        try:
            config = load_experiment_config(path)
        except (OSError, ValueError, KeyError):
            continue
        upsert_experiment(
            connection,
            experiment_id=config.experiment_id,
            pipeline_id=config.pipeline_id,
            title=config.title,
            status=config.status,
            config_path=_repo_relative_config_path(path),
            solution_root=config.result_solution_root,
            payload=experiment_config_to_dict(config),
        )
        registered += 1
    connection.commit()
    return registered
