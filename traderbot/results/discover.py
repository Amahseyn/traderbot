from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from traderbot.results.layout import manifest_parent_dir

_DEFAULT_RESULTS = Path("results")
_DEFAULT_SOLUTIONS = Path("solutions")


@dataclass(frozen=True, slots=True)
class ResultChoice:
    path: Path
    label: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ResultGroup:
    kind: str
    title: str
    runs: tuple[ResultChoice, ...]


def _manifest_at(root: Path, name: str) -> Path | None:
    direct = root / name
    if direct.is_file():
        return direct
    nested = root / "reports" / name
    if nested.is_file():
        return nested
    return None


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _has_charts(path: Path) -> bool:
    viz = path / "visualizations"
    return viz.is_dir() and any(viz.glob("*.png"))


def _dedupe_choices(items: list[ResultChoice]) -> tuple[ResultChoice, ...]:
    seen: set[str] = set()
    out: list[ResultChoice] = []
    for item in sorted(items, key=lambda c: str(c.path)):
        key = str(item.path.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append(ResultChoice(item.path.resolve(), item.label, item.detail))
    return tuple(out)


def _compare_subchoices(compare_dir: Path, manifest: dict) -> tuple[ResultChoice, ...]:
    choices: list[ResultChoice] = [
        ResultChoice(compare_dir, "Overview", "ranking, equity overlay, drawdown, price"),
    ]
    csv_stem = Path(manifest.get("csv", "asset")).stem
    for row in manifest.get("strategies", []):
        sid = row.get("strategy_id", "")
        if not sid:
            continue
        run_dir = compare_dir / "runs" / sid
        if not run_dir.is_dir():
            run_dir = compare_dir / f"{csv_stem}_{sid}"
        if not run_dir.is_dir():
            continue
        ret = row.get("return_pct")
        detail = f"return {ret}%" if ret is not None else ""
        choices.append(ResultChoice(run_dir, sid, detail))
    return tuple(choices)


def _batch_subchoices(batch_dir: Path, manifest: dict) -> tuple[ResultChoice, ...]:
    choices: list[ResultChoice] = []
    for row in manifest.get("runs", []):
        out_raw = row.get("out_dir") or row.get("run_dir")
        if not out_raw:
            continue
        out = Path(out_raw)
        if not out.is_dir():
            out = batch_dir / out.name
        if not out.is_dir():
            continue
        dataset = row.get("dataset") or out.name
        horizon = row.get("horizon_label")
        label = f"{dataset} — {horizon}" if horizon else str(dataset)
        ret = row.get("return_pct")
        detail = f"return {ret}%" if ret is not None else ""
        choices.append(ResultChoice(out, label, detail))
    if not choices and _has_charts(batch_dir):
        choices.append(ResultChoice(batch_dir, "Batch folder", ""))
    return tuple(choices)


def _under_compare(parent: Path, compare_roots: set[Path]) -> bool:
    return any(parent.is_relative_to(c) and parent != c for c in compare_roots)


def discover_result_groups(
    *,
    results_root: Path = _DEFAULT_RESULTS,
    solutions_root: Path = _DEFAULT_SOLUTIONS,
) -> tuple[ResultGroup, ...]:
    compare_dirs: list[Path] = []
    strategy_batches: list[tuple[Path, dict]] = []
    ml_batches: list[tuple[Path, dict]] = []
    backtests: list[ResultChoice] = []
    ml_runs: list[ResultChoice] = []
    live_runs: list[ResultChoice] = []
    compare_roots: set[Path] = set()

    def scan_tree(root: Path) -> None:
        if not root.is_dir():
            return
        for manifest_path in sorted(root.rglob("compare_manifest.json")):
            parent = manifest_parent_dir(manifest_path)
            if parent in compare_roots:
                continue
            compare_roots.add(parent)
            compare_dirs.append(parent)
        for manifest_path in sorted(root.rglob("batch_manifest.json")):
            parent = manifest_parent_dir(manifest_path)
            data = _read_json(manifest_path)
            if "model_id" in data:
                ml_batches.append((parent, data))
            elif "strategy_id" in data:
                strategy_batches.append((parent, data))
            elif manifest_path.parent.name == "reports" and solutions_root in manifest_path.parents:
                ml_batches.append((parent, data))
        for manifest_path in sorted(root.rglob("backtest_summary.json")):
            parent = manifest_path.parent.resolve()
            if _under_compare(parent, compare_roots) or parent in compare_roots:
                continue
            if not _has_charts(parent):
                continue
            summary = _read_json(manifest_path)
            algo = summary.get("algorithm") or summary.get("strategy_id") or parent.name
            ret = summary.get("return_pct")
            detail = f"return {ret}%" if ret is not None else ""
            backtests.append(ResultChoice(parent, str(algo), detail))
        for manifest_path in sorted(root.rglob("results.json")):
            parent = manifest_path.parent.resolve()
            in_batch = any(
                (ancestor / "batch_manifest.json").is_file()
                or (ancestor / "reports" / "batch_manifest.json").is_file()
                for ancestor in (parent, *parent.parents)
            )
            if in_batch or not _has_charts(parent):
                continue
            data = _read_json(manifest_path)
            model = data.get("model_id", "ml")
            horizon = data.get("horizon_label", "")
            label = f"{model} — {horizon}" if horizon else model
            ml_runs.append(
                ResultChoice(parent, label, f"{data.get('n_samples', '?')} holdout samples")
            )
        for manifest_path in sorted(root.rglob("live_markets_manifest.json")):
            parent = manifest_path.parent.resolve()
            if _has_charts(parent):
                live_runs.append(ResultChoice(parent, parent.name, "live dashboard"))

    scan_root = results_root if results_root.exists() else results_root
    scan_tree(scan_root.resolve() if scan_root.exists() else scan_root)
    sol_root = solutions_root if solutions_root.exists() else solutions_root
    scan_tree(sol_root.resolve() if sol_root.exists() else sol_root)

    compare_runs: list[ResultChoice] = []
    for compare_dir in sorted(compare_dirs, key=str):
        manifest_path = _manifest_at(compare_dir, "compare_manifest.json")
        manifest = _read_json(manifest_path) if manifest_path else {}
        best = manifest.get("best_strategy_id")
        csv_name = Path(manifest.get("csv", compare_dir.name)).name
        detail = f"{csv_name}, best: {best}" if best else csv_name
        compare_runs.append(ResultChoice(compare_dir.resolve(), compare_dir.name, detail))

    strategy_batch_runs = [
        ResultChoice(
            batch_dir.resolve(),
            batch_dir.name,
            f"{manifest.get('strategy_id', 'batch')}, {len(manifest.get('runs', []))} CSV(s)",
        )
        for batch_dir, manifest in sorted(strategy_batches, key=lambda x: str(x[0]))
    ]

    ml_batch_runs = [
        ResultChoice(
            batch_dir.resolve(),
            batch_dir.name,
            f"{manifest.get('model_id', 'ml')}, {manifest.get('run_count') or len(manifest.get('runs', []))} run(s)",
        )
        for batch_dir, manifest in sorted(ml_batches, key=lambda x: str(x[0]))
    ]

    groups: list[ResultGroup] = []
    if compare_runs:
        groups.append(ResultGroup("compare", "Strategy compare", tuple(compare_runs)))
    if backtests:
        groups.append(ResultGroup("backtest", "Single strategy backtest", _dedupe_choices(backtests)))
    if strategy_batch_runs:
        groups.append(ResultGroup("strategy_batch", "Strategy batch", tuple(strategy_batch_runs)))
    if ml_runs:
        groups.append(ResultGroup("ml_run", "ML eval run", _dedupe_choices(ml_runs)))
    if ml_batch_runs:
        groups.append(ResultGroup("ml_batch", "ML batch", tuple(ml_batch_runs)))
    if live_runs:
        groups.append(ResultGroup("live", "Live markets", _dedupe_choices(live_runs)))
    return tuple(groups)


def subchoices_for_run(group: ResultGroup, run: ResultChoice) -> tuple[ResultChoice, ...] | None:
    path = run.path
    if group.kind == "compare":
        manifest_path = _manifest_at(path, "compare_manifest.json")
        if manifest_path is not None:
            return _compare_subchoices(path, _read_json(manifest_path))
        return None
    if group.kind in ("strategy_batch", "ml_batch"):
        manifest_path = _manifest_at(path, "batch_manifest.json")
        if manifest_path is not None:
            return _batch_subchoices(path, _read_json(manifest_path))
        return None
    return None
