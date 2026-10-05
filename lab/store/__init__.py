from lab.store.database import default_database_path, open_database
from lab.store.queries import (
    fetch_dashboard_stats,
    fetch_evaluation_run,
    list_compare_sessions,
    list_configurations,
    list_evaluation_runs,
    list_experiments,
)
from traderbot.recording import set_recorder

__all__ = [
    "default_database_path",
    "fetch_dashboard_stats",
    "fetch_evaluation_run",
    "list_compare_sessions",
    "list_configurations",
    "list_evaluation_runs",
    "list_experiments",
    "open_database",
]


def _dispatch_recording(kind: str, **payload):
    from lab.store.bridge import try_record as store_try_record
    from lab.store import hooks

    if kind == "strategy_backtest":
        fields = dict(payload)
        algorithm = fields.pop("algorithm")
        backtest_result = fields.pop("backtest_result")
        store_try_record(
            "strategy backtest",
            lambda: hooks.record_strategy_backtest(algorithm, backtest_result, **fields),
        )
        return
    if kind == "compare_session":
        store_try_record(
            "compare session",
            lambda: hooks.record_compare_session(**payload),
        )
        return
    if kind == "experiment_snapshot":
        store_try_record(
            "experiment snapshot",
            lambda: hooks.record_experiment_snapshot(**payload),
        )


set_recorder(_dispatch_recording)
