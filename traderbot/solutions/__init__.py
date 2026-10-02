"""Standard directory layout for pipeline outputs under ``solutions/``."""

from traderbot.solutions.layout import (
    SOLUTIONS_ROOT,
    SolutionLayout,
    prepare_solution,
    solution_slug,
)

__all__ = [
    "SOLUTIONS_ROOT",
    "SolutionLayout",
    "prepare_solution",
    "solution_slug",
]
