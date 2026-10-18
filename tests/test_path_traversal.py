"""Path-safety regressions for export filenames and Lab job path resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from lab.job_resolvers import JobPayloadError, resolve_lab_file
from traderbot.data.export import safe_export_token


@pytest.mark.parametrize("bad", ["../../etc/passwd", "..", ".", "a/b", "a\\b", "", "  ", "foo\x00bar"])
def test_safe_export_token_rejects_unsafe(bad: str) -> None:
    with pytest.raises(ValueError):
        safe_export_token(bad, field="symbol")


@pytest.mark.parametrize("good", ["BTCIRT", "BTCUSDT", "arb-usdt", "SOL_USDT", "A.B"])
def test_safe_export_token_accepts_market_symbols(good: str) -> None:
    assert safe_export_token(good, field="symbol") == good


def test_resolve_lab_file_rejects_parent_traversal(tmp_path: Path) -> None:
    outside = tmp_path.parent / "escaped.csv"
    outside.write_text("x\n1\n", encoding="utf-8")
    with pytest.raises(JobPayloadError):
        resolve_lab_file(str(tmp_path / ".." / "escaped.csv"), suffixes={".csv"}, field="csv")


def test_resolve_lab_file_rejects_wrong_suffix(tmp_path: Path) -> None:
    secret = tmp_path / "secrets.txt"
    secret.write_text("nope", encoding="utf-8")
    with pytest.raises(JobPayloadError):
        resolve_lab_file(str(secret), suffixes={".csv"}, field="csv")


def test_resolve_lab_file_rejects_missing(tmp_path: Path) -> None:
    with pytest.raises(JobPayloadError):
        resolve_lab_file(str(tmp_path / "missing.csv"), suffixes={".csv"}, field="csv")


def test_resolve_lab_file_accepts_existing_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "BTC_60.csv"
    csv_path.write_text("timestamp,open\n0,1\n", encoding="utf-8")
    resolved = resolve_lab_file(str(csv_path), suffixes={".csv"}, field="csv")
    assert Path(resolved).resolve() == csv_path.resolve()


def test_resolve_lab_file_enforces_allowed_roots(tmp_path: Path, monkeypatch) -> None:
    csv_path = tmp_path / "BTC_60.csv"
    csv_path.write_text("timestamp,open\n0,1\n", encoding="utf-8")
    other_root = tmp_path / "allowed"
    other_root.mkdir()
    monkeypatch.setattr(
        "lab.job_resolvers._allowed_lab_roots", lambda: [other_root.resolve()]
    )
    with pytest.raises(JobPayloadError):
        resolve_lab_file(str(csv_path), suffixes={".csv"}, field="csv")


def test_resolve_lab_file_env_roots_are_added(tmp_path: Path, monkeypatch) -> None:
    extra = tmp_path / "extra"
    extra.mkdir()
    monkeypatch.setenv("TRADERBOT_LAB_PATH_ROOTS", str(extra))
    from lab.job_resolvers import _allowed_lab_roots

    assert extra.resolve() in _allowed_lab_roots()
