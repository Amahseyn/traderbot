"""Domain-agnostic helpers shared outside the trading package."""

from utils.plots import (
    build_subplot_grid_shape,
    configure_matplotlib,
    hide_unused_subplot_axes,
    visualizations_dir,
)
from utils.series import lookup_value_at_or_before, point_at_or_after

__all__ = [
    "build_subplot_grid_shape",
    "configure_matplotlib",
    "hide_unused_subplot_axes",
    "lookup_value_at_or_before",
    "point_at_or_after",
    "visualizations_dir",
]
