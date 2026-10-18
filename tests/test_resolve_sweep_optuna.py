from __future__ import annotations

from pathlib import Path

from lab.job_resolvers import resolve_sweep_body
from lab.store.catalog import upsert_dataset
from lab.store.database import init_database, open_database


def test_resolve_sweep_body_optuna_without_param_grid(tmp_path: Path) -> None:
    csv_path = tmp_path / "BTC_60.csv"
    csv_path.write_text("timestamp,open,high,low,close,volume\n0,1,1,1,1,1\n", encoding="utf-8")
    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    try:
        upsert_dataset(connection, repo_path=str(csv_path), source="test")
        connection.commit()
        prepared = resolve_sweep_body(
            connection,
            {
                "csv": str(csv_path),
                "strategy_id": "sma_cross",
                "mode": "strategies",
                "optimize_method": "optuna",
                "optimize_n_trials": 40,
            },
        )
    finally:
        connection.close()
    assert prepared["optimize_method"] == "optuna"
    assert "param_grid" not in prepared or not prepared.get("param_grid")
