"""Named end-to-end workflows (export → compare → results)."""

from traderbot.pipelines.base import PipelineResult, PipelineStep
from traderbot.pipelines.registry import get_pipeline, list_pipelines, run_pipeline

__all__ = [
    "PipelineResult",
    "PipelineStep",
    "get_pipeline",
    "list_pipelines",
    "run_pipeline",
]
