from lab.store.database import open_database


def test_open_database_creates_sweep_sessions_table(tmp_path):
    database_path = tmp_path / "empty.db"
    connection = open_database(database_path)
    try:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sweep_sessions'",
        ).fetchone()
        assert row is not None
    finally:
        connection.close()
