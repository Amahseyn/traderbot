import json
from pathlib import Path

import pytest

from traderbot.data.export import write_csv
from traderbot.cli.ml import main as ml_main


def _bars(closes: list[float]) -> list[dict]:
    return [
        {
            "symbol": "BTCIRT",
            "resolution": "60",
            "timestamp": i * 3600,
            "datetime_utc": "",
            "open": c,
            "high": c,
            "low": c,
            "close": c,
            "volume": 1.0,
        }
        for i, c in enumerate(closes)
    ]


def _require_lightgbm():
    try:
        import lightgbm as lgb

        return lgb
    except (ImportError, OSError) as exc:
        pytest.skip(f"lightgbm unavailable: {exc}")


def test_ml_cli_run_writes_runs_tree(tmp_path, capsys):
    _require_lightgbm()
    pytest.importorskip("matplotlib")
    csv_path = tmp_path / "BTCIRT_60.csv"
    write_csv(csv_path, _bars([100.0 + 0.01 * i for i in range(60)]))
    experiment = tmp_path / "exp"
    ml_main(
        [
            "run",
            str(csv_path),
            "--model",
            "lightgbm",
            "--horizon-bars",
            "4",
            "--bar-minutes",
            "60",
            "--out",
            str(experiment),
        ]
    )
    runs = list((experiment / "runs").rglob("results.json"))
    assert len(runs) == 1
    assert (experiment / "reports").is_dir()
    assert runs[0].parent.name  # horizon folder
    payload = json.loads(capsys.readouterr().out)
    assert payload["model_id"] == "lightgbm"


def test_ml_cli_batch_writes_reports_manifest(tmp_path, capsys):
    _require_lightgbm()
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    write_csv(csv_dir / "BTCIRT_60.csv", _bars([100.0 + 0.01 * i for i in range(60)]))
    write_csv(csv_dir / "ETHIRT_60.csv", _bars([200.0 + 0.01 * i for i in range(60)]))
    out = tmp_path / "batch"
    ml_main(["batch", str(csv_dir), "--out", str(out), "--no-plots"])
    manifest_path = out / "reports" / "batch_manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_count"] == 2
    assert all(Path(row["out_dir"]).is_dir() for row in manifest["runs"])
    assert all("runs" in row["out_dir"] for row in manifest["runs"])
    summary = json.loads(capsys.readouterr().out)
    assert summary["manifest"] == str(manifest_path)
