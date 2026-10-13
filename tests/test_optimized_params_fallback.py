import json
import sqlite3
from pathlib import Path

from traderbot.algorithms.optimized_params import (
    fallback_sweep_symbols,
    resolve_best_sweep_params,
    sweep_symbol_candidates,
)


def _init_sweep_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE sweep_sessions (
            id TEXT PRIMARY KEY,
            strategy_id TEXT,
            symbol TEXT,
            resolution TEXT,
            best_params_json TEXT,
            created_at_utc TEXT
        );
        """
    )
    connection.execute(
        """
        INSERT INTO sweep_sessions (id, strategy_id, symbol, resolution, best_params_json, created_at_utc)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "1",
            "sma_cross",
            "BTCIRT",
            "60",
            json.dumps({"fast": 7, "slow": 21}),
            "2026-01-01T00:00:00Z",
        ),
    )
    connection.commit()
    connection.close()


def test_fallback_symbol_lists():
    assert "BTCIRT" in fallback_sweep_symbols("ADAIRT")
    assert "BTCUSDT" in fallback_sweep_symbols("ETHUSDT")


def test_sweep_symbol_candidates_prefers_primary():
    assert sweep_symbol_candidates("ADAIRT")[0] == "ADAIRT"


def test_resolve_best_sweep_params_uses_fallback(tmp_path):
    db_path = tmp_path / "t.db"
    _init_sweep_db(db_path)
    params, matched = resolve_best_sweep_params(
        "sma_cross",
        symbol="ADAIRT",
        resolution="60",
        database_path=db_path,
    )
    assert matched == "BTCIRT"
    assert params == {"fast": 7, "slow": 21}
