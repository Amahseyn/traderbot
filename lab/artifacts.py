from __future__ import annotations

from pathlib import Path
from typing import Any

from lab.store.constants import REPO_ROOT

DEFAULT_CSV_LIST_LIMIT = 200
MAX_CSV_LIST_LIMIT = 500


def _artifact_allowed_roots() -> tuple[Path, ...]:
    return (
        REPO_ROOT / "results",
        REPO_ROOT / "solutions",
        REPO_ROOT / "data",
    )


def resolve_artifact_path(relative_path: str) -> Path | None:
    """Map a repo-relative (or absolute under-repo) path to an allowed file."""
    raw = Path(relative_path)
    candidate = raw.resolve() if raw.is_absolute() else (REPO_ROOT / relative_path).resolve()
    try:
        candidate.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    for root in _artifact_allowed_roots():
        try:
            candidate.relative_to(root.resolve())
            return candidate
        except ValueError:
            continue
    return None


def artifact_relpath_for_out_dir(artifact_path: str, out_dir: str) -> str:
    """Relative path under ``out_dir`` for run artifact query strings (may include subdirs)."""
    out_root = Path(out_dir).resolve()
    raw = Path(artifact_path)
    resolved = raw.resolve() if raw.is_absolute() else (REPO_ROOT / artifact_path).resolve()
    try:
        return resolved.relative_to(out_root).as_posix()
    except ValueError:
        return raw.name


def resolve_run_artifact(out_dir: str, file_query: str) -> Path | None:
    """Resolve ``?file=`` for a catalog run; path must stay under ``out_dir``."""
    from pathlib import PurePosixPath

    rel = PurePosixPath(file_query)
    if rel.is_absolute() or ".." in rel.parts:
        return None
    out_root = Path(out_dir).resolve()
    candidate = (out_root / rel).resolve()
    try:
        candidate.relative_to(out_root)
    except ValueError:
        return None
    if not candidate.is_file() and file_query == "results.json":
        summary = out_root / "backtest_summary.json"
        if summary.is_file():
            candidate = summary.resolve()
    return resolve_artifact_path(str(candidate))


def list_png_artifacts_for_run(out_dir: str) -> list[str]:
    root = Path(out_dir)
    if not root.is_dir():
        return []
    paths: list[str] = []
    for png in sorted(root.rglob("*.png")):
        try:
            paths.append(str(png.resolve().relative_to(REPO_ROOT.resolve())))
        except ValueError:
            continue
    return paths


def list_data_csv_files(limit: int = DEFAULT_CSV_LIST_LIMIT) -> list[dict[str, Any]]:
    """Repo-relative OHLC CSV paths under ``data/`` for Lab download browser."""
    capped = min(max(limit, 1), MAX_CSV_LIST_LIMIT)
    data_root = REPO_ROOT / "data"
    if not data_root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for csv_path in sorted(data_root.rglob("*.csv")):
        if not csv_path.is_file():
            continue
        try:
            relative = str(csv_path.resolve().relative_to(REPO_ROOT.resolve()))
        except ValueError:
            continue
        stat = csv_path.stat()
        rows.append(
            {
                "path": relative,
                "size_bytes": stat.st_size,
                "modified_at_utc": stat.st_mtime,
            },
        )
        if len(rows) >= capped:
            break
    return rows
