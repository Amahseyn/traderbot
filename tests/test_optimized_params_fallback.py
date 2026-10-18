import json
import sqlite3
from pathlib import Path

from traderbot.algorithms.optimized_params import (
    fallback_sweep_symbols,
    horizon_label_from_csv_path,
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


def _insert_sweep_row(
    connection: sqlite3.Connection,
    *,
    row_id: str,
    strategy_id: str,
    symbol: str,
    resolution: str,
    best_params: dict,
    created_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO sweep_sessions (id, strategy_id, symbol, resolution, best_params_json, created_at_utc)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            row_id,
            strategy_id,
            symbol,
            resolution,
            json.dumps(best_params),
            created_at,
        ),
    )


def test_resolve_best_sweep_params_scoped_by_resolution(tmp_path):
    db_path = tmp_path / "t.db"
    _init_sweep_db(db_path)
    connection = sqlite3.connect(db_path)
    _insert_sweep_row(
        connection,
        row_id="2",
        strategy_id="sma_cross",
        symbol="BTCIRT",
        resolution="240",
        best_params={"fast": 99, "slow": 88},
        created_at="2026-02-01T00:00:00Z",
    )
    connection.commit()
    connection.close()

    params_60, symbol_60 = resolve_best_sweep_params(
        "sma_cross", symbol="BTCIRT", resolution="60", database_path=db_path
    )
    params_240, symbol_240 = resolve_best_sweep_params(
        "sma_cross", symbol="BTCIRT", resolution="240", database_path=db_path
    )
    assert symbol_60 == "BTCIRT" and params_60 == {"fast": 7, "slow": 21}
    assert symbol_240 == "BTCIRT" and params_240 == {"fast": 99, "slow": 88}

    assert resolve_best_sweep_params(
        "sma_cross", symbol="BTCIRT", resolution="15", database_path=db_path
    ) == (None, None)


def test_resolve_optimized_namespace_applies_sweep_per_resolution(tmp_path):
    from traderbot.algorithms.optimized_params import resolve_optimized_namespace

    db_path = tmp_path / "t.db"
    _init_sweep_db(db_path)
    connection = sqlite3.connect(db_path)
    _insert_sweep_row(
        connection,
        row_id="2",
        strategy_id="sma_cross",
        symbol="BTCIRT",
        resolution="240",
        best_params={"fast": 4, "slow": 40},
        created_at="2026-02-01T00:00:00Z",
    )
    connection.commit()
    connection.close()

    namespace_60 = resolve_optimized_namespace(
        "sma_cross",
        symbol="BTCIRT",
        resolution="60",
        database_path=db_path,
        apply_sweep_winner=True,
    )
    namespace_240 = resolve_optimized_namespace(
        "sma_cross",
        symbol="BTCIRT",
        resolution="240",
        database_path=db_path,
        apply_sweep_winner=True,
    )
    assert namespace_60.fast == 7 and namespace_60.slow == 21
    assert namespace_240.fast == 4 and namespace_240.slow == 40


def test_horizon_label_from_csv_path():
    assert horizon_label_from_csv_path("data/crypto/horizons/12h/ETHUSDT_720.csv") == "12h"
    assert horizon_label_from_csv_path("data/crypto/ohlc/ETHUSDT_720.csv") is None
    assert horizon_label_from_csv_path(None) is None


def _init_horizon_sweep_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE sweep_sessions (
            id TEXT PRIMARY KEY,
            strategy_id TEXT,
            symbol TEXT,
            resolution TEXT,
            horizon_label TEXT,
            best_params_json TEXT,
            created_at_utc TEXT
        );
        """
    )
    connection.commit()
    connection.close()


def _insert_horizon_row(
    connection: sqlite3.Connection,
    *,
    row_id: str,
    symbol: str,
    resolution: str,
    horizon_label: str | None,
    best_params: dict,
    created_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO sweep_sessions
            (id, strategy_id, symbol, resolution, horizon_label, best_params_json, created_at_utc)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row_id,
            "sma_cross",
            symbol,
            resolution,
            horizon_label,
            json.dumps(best_params),
            created_at,
        ),
    )


def test_resolve_best_sweep_params_prefers_matching_horizon(tmp_path):
    db_path = tmp_path / "t.db"
    _init_horizon_sweep_db(db_path)
    connection = sqlite3.connect(db_path)
    _insert_horizon_row(
        connection,
        row_id="12h",
        symbol="ETHUSDT",
        resolution="720",
        horizon_label="12h",
        best_params={"fast": 12, "slow": 24},
        created_at="2026-01-01T00:00:00Z",
    )
    _insert_horizon_row(
        connection,
        row_id="1d",
        symbol="ETHUSDT",
        resolution="720",
        horizon_label="1d",
        best_params={"fast": 24, "slow": 48},
        created_at="2026-01-02T00:00:00Z",
    )
    _insert_horizon_row(
        connection,
        row_id="plain",
        symbol="ETHUSDT",
        resolution="720",
        horizon_label=None,
        best_params={"fast": 7, "slow": 21},
        created_at="2026-01-03T00:00:00Z",
    )
    connection.commit()
    connection.close()

    params_12h, _ = resolve_best_sweep_params(
        "sma_cross", symbol="ETHUSDT", resolution="720", horizon_label="12h", database_path=db_path
    )
    params_1d, _ = resolve_best_sweep_params(
        "sma_cross", symbol="ETHUSDT", resolution="720", horizon_label="1d", database_path=db_path
    )
    params_plain, _ = resolve_best_sweep_params(
        "sma_cross", symbol="ETHUSDT", resolution="720", database_path=db_path
    )
    assert params_12h == {"fast": 12, "slow": 24}
    assert params_1d == {"fast": 24, "slow": 48}
    assert params_plain == {"fast": 7, "slow": 21}


def test_resolve_best_sweep_params_horizon_fallbacks(tmp_path):
    db_path = tmp_path / "t.db"
    _init_horizon_sweep_db(db_path)
    connection = sqlite3.connect(db_path)
    _insert_horizon_row(
        connection,
        row_id="12h",
        symbol="ETHUSDT",
        resolution="720",
        horizon_label="12h",
        best_params={"fast": 12, "slow": 24},
        created_at="2026-01-01T00:00:00Z",
    )
    _insert_horizon_row(
        connection,
        row_id="plain",
        symbol="ETHUSDT",
        resolution="720",
        horizon_label=None,
        best_params={"fast": 7, "slow": 21},
        created_at="2026-01-02T00:00:00Z",
    )
    connection.commit()
    connection.close()

    # No 1d row: prefer unlabeled rows over a different horizon label.
    params, _ = resolve_best_sweep_params(
        "sma_cross", symbol="ETHUSDT", resolution="720", horizon_label="1d", database_path=db_path
    )
    assert params == {"fast": 7, "slow": 21}

    connection = sqlite3.connect(db_path)
    connection.execute("DELETE FROM sweep_sessions WHERE horizon_label IS NULL")
    connection.commit()
    connection.close()

    # No unlabeled row either: fall back to any horizon row rather than nothing.
    params, _ = resolve_best_sweep_params(
        "sma_cross", symbol="ETHUSDT", resolution="720", horizon_label="1d", database_path=db_path
    )
    assert params == {"fast": 12, "slow": 24}
