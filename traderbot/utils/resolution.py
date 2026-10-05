from __future__ import annotations


def resolution_minutes(resolution: str) -> int:
    if resolution.isdigit():
        return int(resolution)
    if resolution == "D":
        return 24 * 60
    if resolution == "2D":
        return 2 * 24 * 60
    if resolution == "3D":
        return 3 * 24 * 60
    raise ValueError(f"unknown resolution: {resolution}")


def resolution_from_csv_path(csv_path: str) -> str:
    """``BTCIRT_60.csv`` -> ``60``."""
    return csv_path.rsplit("_", 1)[-1].removesuffix(".csv")
