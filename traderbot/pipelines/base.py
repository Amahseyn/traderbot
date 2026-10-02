from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PipelineStep:
    name: str
    detail: str = ""
    artifacts: list[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    pipeline_id: str
    steps: list[PipelineStep] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)

    def add_step(self, name: str, *, detail: str = "", artifacts: list[str | Path] | None = None) -> None:
        paths = [str(a) for a in (artifacts or [])]
        self.steps.append(PipelineStep(name=name, detail=detail, artifacts=paths))

    def write_summary(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "pipeline_id": self.pipeline_id,
            "steps": [s.__dict__ for s in self.steps],
            "outputs": self.outputs,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path


PipelineFn = Callable[..., PipelineResult]
