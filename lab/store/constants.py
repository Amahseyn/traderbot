from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

CONFIG_KIND_STRATEGY = "strategy"
CONFIG_KIND_MODEL = "model"
CONFIG_KIND_EXPERIMENT = "experiment"

RUN_KIND_STRATEGY_BACKTEST = "strategy_backtest"
RUN_KIND_MODEL_FORECAST = "model_forecast"

JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"
JOB_STATUS_CANCELLED = "cancelled"
