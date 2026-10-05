from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from inspect import Parameter, signature
from pathlib import Path
from typing import Any

from traderbot.pipelines.registry import get_pipeline, run_pipeline
from traderbot.solutions.layout import solution_slug
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXPERIMENT_CONFIG_DIR = REPO_ROOT / "config"

EXPERIMENT_SCHEMA_VERSION = 1
EXPERIMENT_STATUSES = frozenset({"pending", "running", "completed", "failed", "skipped"})

_PATH_PARAM_KEYS = frozenset(
    {
        "csv",
        "csv_path",
        "data_dir",
        "results_dir",
        "solution_root",
        "solutions_root",
        "jobs_file",
    }
)


@dataclass
class ExperimentConfig:
    """Declarative experiment: pipeline id, params, optional test_steps, and run status."""

    experiment_id: str
    pipeline_id: str
    title: str = ""
    status: str = "pending"
    schema_version: int = EXPERIMENT_SCHEMA_VERSION
    solutions_root: str = "solutions"
    solution_root: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    test_steps: list[dict[str, Any]] = field(default_factory=list)
    started_at_utc: str | None = None
    completed_at_utc: str | None = None
    last_error: str | None = None
    result_solution_root: str | None = None
    comment: str | None = None

    def validate(self) -> None:
        if self.schema_version != EXPERIMENT_SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version={self.schema_version}")
        if self.status not in EXPERIMENT_STATUSES:
            raise ValueError(f"status must be one of {sorted(EXPERIMENT_STATUSES)}")
        get_pipeline(self.pipeline_id)
        seen_step_ids: set[str] = set()
        for step in self.test_steps:
            step_id = step.get("step_id")
            if not step_id:
                raise ValueError("each test_steps entry needs step_id")
            if step_id in seen_step_ids:
                raise ValueError(f"duplicate test_steps step_id={step_id!r}")
            seen_step_ids.add(str(step_id))
            step_status = step.get("status", "pending")
            if step_status not in EXPERIMENT_STATUSES:
                raise ValueError(f"invalid step status for {step_id!r}")


def resolve_one_hour_window_params(params: dict[str, Any]) -> dict[str, Any]:
    """
    For 1h OHLC experiments: ``window_hours`` is the **holdout eval window** (recent hours).

    Maps to ``holdout_tail_bars`` (one bar per hour on ``*_60.csv``). Training uses the
    full on-disk CSV; only ML metrics and ``holdout_return_pct`` strategies use this tail.
    ``null`` = no fixed tail (temporal train/holdout split on all data).

    Explicit ``tail_bars`` still slices the entire CSV to the last N bars (legacy smoke).

    ``train_supervised_row_count`` applies only when ``holdout_tail_bars`` is unset.
    """
    merged = dict(params)
    if "holdout_tail_bars" not in merged and "window_hours" in merged:
        merged["holdout_tail_bars"] = merged["window_hours"]
    return merged


def apply_experiment_param_defaults(params: dict[str, Any]) -> dict[str, Any]:
    merged = resolve_one_hour_window_params(params)
    merged.pop("model_id", None)
    merged.pop("run_lightgbm", None)
    merged.pop("num_boost_round", None)
    merged.pop("train_supervised_row_count", None)
    return merged


def normalize_experiment_config(config: ExperimentConfig) -> None:
    config.params = apply_experiment_param_defaults(config.params)
    for step in config.test_steps:
        step_params = step.get("params") or {}
        if not isinstance(step_params, dict):
            raise ValueError("test_steps[].params must be an object")
        step["params"] = apply_experiment_param_defaults(step_params)


def load_experiment_config(path: Path) -> ExperimentConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("experiment config must be a JSON object")
    params = raw.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError("params must be an object")
    test_steps = raw.get("test_steps") or []
    if not isinstance(test_steps, list):
        raise ValueError("test_steps must be a list")
    config = ExperimentConfig(
        experiment_id=str(raw["experiment_id"]),
        pipeline_id=str(raw["pipeline_id"]),
        title=str(raw.get("title") or raw["experiment_id"]),
        status=str(raw.get("status", "pending")),
        schema_version=int(raw.get("schema_version", EXPERIMENT_SCHEMA_VERSION)),
        solutions_root=str(raw.get("solutions_root", "solutions")),
        solution_root=raw.get("solution_root"),
        params=dict(params),
        test_steps=[dict(step) for step in test_steps],
        started_at_utc=raw.get("started_at_utc"),
        completed_at_utc=raw.get("completed_at_utc"),
        last_error=raw.get("last_error"),
        result_solution_root=raw.get("result_solution_root"),
        comment=raw.get("comment"),
    )
    normalize_experiment_config(config)
    config.validate()
    return config


def save_experiment_config(path: Path, config: ExperimentConfig) -> None:
    payload = experiment_config_to_dict(config)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def experiment_config_to_dict(config: ExperimentConfig) -> dict[str, Any]:
    body = asdict(config)
    comment = body.pop("comment", None)
    if not body.get("test_steps"):
        body.pop("test_steps", None)
    if comment:
        return {"comment": comment, **body}
    return body


def merge_experiment_params(
    config: ExperimentConfig,
    step: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Base ``params`` merged with a test step's ``params`` (step wins), then ML defaults."""
    merged = dict(config.params)
    if step is not None:
        step_params = step.get("params") or {}
        if not isinstance(step_params, dict):
            raise ValueError("test_steps[].params must be an object")
        merged.update(step_params)
    return apply_experiment_param_defaults(merged)


def _coerce_param_value(key: str, value: Any) -> Any:
    if value is None:
        return None
    if key in _PATH_PARAM_KEYS or key.endswith("_path"):
        return Path(value)
    return value


def build_pipeline_kwargs(
    config: ExperimentConfig,
    *,
    param_overrides: dict[str, Any] | None = None,
    results_dir: Path | None = None,
) -> dict[str, Any]:
    """Map merged experiment params to ``run_pipeline`` keyword arguments."""
    spec = get_pipeline(config.pipeline_id)
    try:
        sig_params = signature(spec.fn).parameters
        accepts_var_kw = any(p.kind == Parameter.VAR_KEYWORD for p in sig_params.values())
        accepted = None if accepts_var_kw else set(sig_params)
    except (TypeError, ValueError):
        accepted = None

    merged = dict(config.params)
    if param_overrides:
        merged.update(param_overrides)

    kwargs: dict[str, Any] = {
        "solutions_root": Path(config.solutions_root),
    }
    if results_dir is not None:
        kwargs["results_dir"] = results_dir
    elif config.solution_root:
        kwargs["results_dir"] = Path(config.solution_root)

    for key, value in merged.items():
        param_key = "csv_path" if key == "csv" else key
        if accepted is not None and param_key not in accepted:
            continue
        kwargs[param_key] = _coerce_param_value(param_key, value)

    return kwargs


def experiment_is_completed(config: ExperimentConfig) -> bool:
    if config.test_steps:
        return all(step.get("status") == "completed" for step in config.test_steps)
    return config.status == "completed"


def resolve_step_results_dir(config: ExperimentConfig, step_id: str) -> Path:
    slug = solution_slug(config.pipeline_id)
    if config.solution_root:
        base = Path(config.solution_root)
    else:
        base = Path(config.solutions_root) / slug / config.experiment_id
    return base / step_id


def resolve_run_results_dir(config: ExperimentConfig, step: dict[str, Any]) -> Path:
    """Output tree for one run (flat when ``test_steps`` is omitted)."""
    if not config.test_steps:
        if config.solution_root:
            return Path(config.solution_root)
        return Path(config.solutions_root) / solution_slug(config.pipeline_id)
    return resolve_step_results_dir(config, str(step["step_id"]))


def _sync_experiment_status_from_steps(config: ExperimentConfig) -> None:
    if not config.test_steps:
        return
    statuses = {step.get("status", "pending") for step in config.test_steps}
    if statuses == {"completed"}:
        config.status = "completed"
    elif "failed" in statuses:
        config.status = "failed"
    elif "running" in statuses:
        config.status = "running"
    elif config.status != "skipped":
        config.status = "pending"


def run_experiment_config(
    path: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    step_id: str | None = None,
    param_overrides: dict[str, Any] | None = None,
    step_param_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Load config, run pipeline (once or per ``test_steps``), update status on disk.

    Skips when completed unless ``force`` is true. Use ``step_id`` to run one step only.
    """
    config_path = path.resolve()
    config = load_experiment_config(config_path)
    if param_overrides:
        config.params.update(param_overrides)
    if step_param_overrides:
        for step in config.test_steps:
            extra = step_param_overrides.get(str(step.get("step_id")))
            if isinstance(extra, dict):
                params = step.get("params") or {}
                if not isinstance(params, dict):
                    raise ValueError("test_steps[].params must be an object")
                params.update(extra)
                step["params"] = params

    if experiment_is_completed(config) and not force:
        return {
            "skipped": True,
            "reason": "already completed",
            "experiment_id": config.experiment_id,
            "config": str(config_path),
            "result_solution_root": config.result_solution_root,
        }

    steps_to_run = config.test_steps
    if not steps_to_run:
        steps_to_run = [
            {
                "step_id": "default",
                "title": config.title,
                "status": config.status,
                "params": {},
            }
        ]

    if step_id is not None:
        steps_to_run = [s for s in steps_to_run if s.get("step_id") == step_id]
        if not steps_to_run:
            raise KeyError(f"unknown test_steps step_id={step_id!r}")

    if dry_run:
        previews = []
        for step in steps_to_run:
            merged = merge_experiment_params(config, step)
            step_root = resolve_run_results_dir(config, step)
            previews.append(
                {
                    "step_id": step["step_id"],
                    "title": step.get("title", ""),
                    "status": step.get("status", "pending"),
                    "params": merged,
                    "kwargs": {
                        k: str(v) for k, v in build_pipeline_kwargs(
                            config,
                            param_overrides=merged,
                            results_dir=step_root,
                        ).items()
                    },
                }
            )
        body: dict[str, Any] = {
            "dry_run": True,
            "experiment_id": config.experiment_id,
            "pipeline_id": config.pipeline_id,
            "test_steps": previews,
        }
        if len(previews) == 1:
            body["kwargs"] = previews[0]["kwargs"]
        return body

    config.status = "running"
    config.started_at_utc = datetime.now(timezone.utc).isoformat()
    config.last_error = None
    save_experiment_config(config_path, config)

    step_results: list[dict[str, Any]] = []
    last_solution_root: str | None = None

    try:
        for step in steps_to_run:
            sid = str(step["step_id"])
            if step.get("status") == "completed" and not force:
                step_results.append({"step_id": sid, "skipped": True, "reason": "completed"})
                continue

            merged = merge_experiment_params(config, step)
            step_root = resolve_run_results_dir(config, step)
            step["status"] = "running"
            if config.test_steps:
                save_experiment_config(config_path, config)

            result = run_pipeline(
                config.pipeline_id,
                **build_pipeline_kwargs(
                    config,
                    param_overrides=merged,
                    results_dir=step_root,
                ),
            )
            solution_root = result.outputs.get("solution_root")
            last_solution_root = str(solution_root) if solution_root else None
            step["status"] = "completed"
            step["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
            step["last_error"] = None
            step["result_solution_root"] = last_solution_root
            if config.test_steps:
                save_experiment_config(config_path, config)

            if solution_root:
                report_copy = Path(solution_root) / "reports" / "experiment_config.json"
                report_copy.parent.mkdir(parents=True, exist_ok=True)
                save_experiment_config(report_copy, config)

            step_results.append(
                {
                    "step_id": sid,
                    "skipped": False,
                    "result_solution_root": last_solution_root,
                    "outputs": result.outputs,
                }
            )
    except Exception as exc:
        config.status = "failed"
        config.completed_at_utc = datetime.now(timezone.utc).isoformat()
        config.last_error = str(exc)
        for step in steps_to_run:
            if step.get("status") == "running":
                step["status"] = "failed"
                step["last_error"] = str(exc)
        _sync_experiment_status_from_steps(config)
        save_experiment_config(config_path, config)
        raise

    config.completed_at_utc = datetime.now(timezone.utc).isoformat()
    config.last_error = None
    config.result_solution_root = last_solution_root
    _sync_experiment_status_from_steps(config)
    if not config.test_steps:
        config.status = "completed"
    save_experiment_config(config_path, config)

    from traderbot.recording import try_record

    try_record(
        "experiment_snapshot",
        experiment_id=config.experiment_id,
        pipeline_id=config.pipeline_id,
        title=config.title,
        status=config.status,
        config_path=str(config_path),
        solution_root=config.result_solution_root,
        payload=asdict(config),
    )

    return {
        "skipped": False,
        "experiment_id": config.experiment_id,
        "pipeline_id": config.pipeline_id,
        "status": config.status,
        "config": str(config_path),
        "result_solution_root": config.result_solution_root,
        "steps": step_results,
    }
