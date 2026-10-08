from __future__ import annotations

from pathlib import Path

from traderbot.backtesting.horizon_tune import (
    dataset_horizon_label_for_csv,
    filter_csv_paths_for_horizon_tuning,
)


def test_dataset_horizon_label_for_csv():
    assert dataset_horizon_label_for_csv(Path("BTCIRT_1.csv")) == "1m"
    assert dataset_horizon_label_for_csv(Path("ETHIRT_5.csv")) == "5m"
    assert dataset_horizon_label_for_csv(Path("ETHIRT_15.csv")) == "15m"
    assert dataset_horizon_label_for_csv(Path("BTCIRT_60.csv")) == "1h"
    assert dataset_horizon_label_for_csv(Path("ETHIRT_240.csv")) == "4h"
    assert dataset_horizon_label_for_csv(Path("BTCIRT_D.csv")) == "1d"


def test_filter_csv_paths_for_horizon_tuning_excludes_mismatched_bar_period():
    paths = [
        Path("BTCIRT_60.csv"),
        Path("ETHIRT_15.csv"),
        Path("ETHIRT_5.csv"),
    ]
    assert filter_csv_paths_for_horizon_tuning(paths, "1h") == [Path("BTCIRT_60.csv")]
    assert filter_csv_paths_for_horizon_tuning(paths, "5m") == [Path("ETHIRT_5.csv")]
