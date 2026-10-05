from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from traderbot.algorithms.base import Algorithm
from traderbot.backtesting.engine import BacktestResult
from utils.plots import configure_matplotlib, visualizations_dir


# Distinct, colorblind-friendly palette (Okabe–Ito inspired)
def add_visualization_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--visualize",
        action="store_true",
        help="Write full PNG charts (requires matplotlib; default when --out is set)",
    )
    parser.add_argument(
        "--no-visualize",
        action="store_true",
        help="Skip all chart output",
    )
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="Alias for --no-visualize",
    )


def wants_visualization(args: argparse.Namespace, *, has_out: bool) -> bool:
    if args.no_visualize or args.no_plot:
        return False
    if args.visualize:
        return True
    return has_out


_STRATEGY_COLORS = (
    "#0072B2",
    "#E69F00",
    "#009E73",
    "#CC79A7",
    "#D55E00",
    "#56B4E9",
)


@dataclass(frozen=True, slots=True)
class BacktestVisualizationPaths:
    equity_curve: Path
    drawdown: Path
    price_trades: Path


@dataclass(frozen=True, slots=True)
class CompareVisualizationPaths:
    strategy_ranking: Path
    equity_overlay: Path
    drawdown_overlay: Path
    asset_price: Path


def buy_hold_equity_curve(
    bars: Sequence[dict[str, Any]],
    initial_cash: float,
) -> list[tuple[int, float]]:
    if not bars or initial_cash <= 0:
        return []
    first_close = float(bars[0]["close"])
    if first_close <= 0:
        return []
    out: list[tuple[int, float]] = []
    for bar in bars:
        ts = int(bar["timestamp"])
        close = float(bar["close"])
        equity = initial_cash * (close / first_close)
        out.append((ts, equity))
    return out


def _drawdown_series(equity_curve: Sequence[tuple[int, float]]) -> list[tuple[int, float]]:
    peak = 0.0
    out: list[tuple[int, float]] = []
    for ts, eq in equity_curve:
        peak = max(peak, eq)
        dd_pct = 0.0 if peak <= 0 else (eq / peak - 1.0) * 100.0
        out.append((ts, dd_pct))
    return out


def _setup_style() -> None:
    import matplotlib as mpl

    configure_matplotlib(interactive=False)
    mpl.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "#fafafa",
            "axes.edgecolor": "#cbd5e1",
            "axes.labelcolor": "#334155",
            "axes.titleweight": "bold",
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "xtick.color": "#64748b",
            "ytick.color": "#64748b",
            "grid.color": "#e2e8f0",
            "grid.linewidth": 0.6,
            "legend.framealpha": 0.95,
            "legend.edgecolor": "#e2e8f0",
            "font.size": 9,
        }
    )


def _x_values(bars: Sequence[dict[str, Any]], timestamps: Sequence[int]) -> list[Any]:
    if len(bars) == len(timestamps):
        labels = [str(b.get("datetime_utc") or "").strip() for b in bars]
        if any(labels):
            return labels
    return list(range(len(timestamps)))


def _x_axis_label(bars: Sequence[dict[str, Any]], timestamps: Sequence[int]) -> str:
    if len(bars) == len(timestamps):
        labels = [str(b.get("datetime_utc") or "").strip() for b in bars]
        if any(labels):
            return "Time (UTC)"
    return "Bar index"


def _close_price_label(bars: Sequence[dict[str, Any]]) -> str:
    if not bars:
        return "Close"
    symbol = str(bars[0].get("symbol") or "").strip()
    return f"Close ({symbol})" if symbol else "Close"


def _format_price_axis(ax) -> None:
    from matplotlib.ticker import FuncFormatter

    def _tick(value: float, _pos: int) -> str:
        abs_v = abs(value)
        if abs_v >= 1e9:
            return f"{value / 1e9:.2f}B"
        if abs_v >= 1e6:
            return f"{value / 1e6:.2f}M"
        if abs_v >= 1e3:
            return f"{value / 1e3:.2f}K"
        return f"{value:.4g}"

    ax.yaxis.set_major_formatter(FuncFormatter(_tick))


def _plot_market_close(
    ax,
    bars: Sequence[dict[str, Any]],
    xs: Sequence[Any],
    *,
    linewidth = 1.0,
    color = "#475569",
    label = "Close",
) -> list[float]:
    closes = [float(b["close"]) for b in bars]
    ax.plot(xs, closes, color=color, linewidth=linewidth, label=label, zorder=1)
    return closes


def _annotate_summary(ax, *, title: str, lines: list[str]) -> None:
    body = "\n".join(lines)
    ax.text(
        0.02,
        0.98,
        f"{title}\n{body}",
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=8,
        family="monospace",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "#cbd5e1", "alpha": 0.94},
    )


def render_backtest_plots(
    algorithm: Algorithm,
    result: BacktestResult,
    bars: Sequence[dict[str, Any]],
    out_dir: Path,
) -> BacktestVisualizationPaths:
    """Write equity, drawdown, and price+trade charts under ``out_dir/visualizations``."""
    import matplotlib.pyplot as plt

    _setup_style()
    plots_dir = visualizations_dir(out_dir)
    bh = buy_hold_equity_curve(bars, result.initial_cash)
    ts_eq = [ts for ts, _ in result.equity_curve]
    strat_eq = [eq for _, eq in result.equity_curve]
    xs = _x_values(bars, ts_eq)

    equity_path = plots_dir / "equity_curve.png"
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.plot(xs, strat_eq, color="#2563eb", linewidth=1.5, label="Strategy", zorder=3)
    if bh:
        ax.plot(xs, [eq for _, eq in bh], color="#f59e0b", linewidth=1.1, alpha=0.9, label="Buy & hold")
    ax.axhline(result.initial_cash, color="#94a3b8", linestyle="--", linewidth=0.8, label="Initial cash")
    ax.set_title(f"{algorithm.name} — portfolio equity (not asset price)")
    ax.set_xlabel("Bar")
    ax.set_ylabel("Portfolio value (cash)")
    ax.grid(True, axis="y", alpha=0.85)
    ax.legend(loc="upper left", fontsize=8)
    _annotate_summary(
        ax,
        title="Summary",
        lines=[
            f"return: {result.return_pct:+.2f}%",
            f"trades: {len(result.trades)}",
            f"final: {result.final_equity:,.2f}",
        ],
    )
    if len(xs) > 40:
        ax.tick_params(axis="x", labelrotation=45, labelsize=7)
    fig.tight_layout()
    fig.savefig(equity_path, dpi=140)
    plt.close(fig)

    dd_path = plots_dir / "drawdown.png"
    dd = _drawdown_series(result.equity_curve)
    fig, ax = plt.subplots(figsize=(10, 3.2))
    ax.fill_between(xs, [v for _, v in dd], 0.0, color="#ef4444", alpha=0.35)
    ax.plot(xs, [v for _, v in dd], color="#b91c1c", linewidth=1.0)
    ax.set_title(f"{algorithm.name} — drawdown")
    ax.set_xlabel("Bar")
    ax.set_ylabel("Drawdown %")
    ax.grid(True, axis="y", alpha=0.85)
    fig.tight_layout()
    fig.savefig(dd_path, dpi=140)
    plt.close(fig)

    price_path = plots_dir / "price_trades.png"
    fig, ax = plt.subplots(figsize=(10, 4.2))
    closes = _plot_market_close(ax, bars, xs, label="Close")
    buy_ts = {t.timestamp for t in result.trades if t.action == "buy"}
    sell_ts = {t.timestamp for t in result.trades if t.action == "sell"}
    buy_x = [i for i, ts in enumerate(ts_eq) if ts in buy_ts]
    sell_x = [i for i, ts in enumerate(ts_eq) if ts in sell_ts]
    buy_y = [closes[i] for i in buy_x]
    sell_y = [closes[i] for i in sell_x]
    if buy_x:
        ax.scatter(
            buy_x, buy_y, marker="^", color="#16a34a", s=42, label="Buy", zorder=4, edgecolors="white", linewidths=0.4
        )
    if sell_x:
        ax.scatter(
            sell_x,
            sell_y,
            marker="v",
            color="#dc2626",
            s=42,
            label="Sell",
            zorder=4,
            edgecolors="white",
            linewidths=0.4,
        )
    ax.set_title(f"{algorithm.name} — market close & signals")
    ax.set_xlabel(_x_axis_label(bars, ts_eq))
    ax.set_ylabel(_close_price_label(bars))
    _format_price_axis(ax)
    ax.grid(True, axis="y", alpha=0.85)
    ax.legend(loc="upper left", fontsize=8)
    if closes:
        last = closes[-1]
        _annotate_summary(
            ax,
            title="Last close",
            lines=[f"{last:,.2f}"],
        )
    if len(xs) > 40:
        ax.tick_params(axis="x", labelrotation=45, labelsize=7)
    fig.tight_layout()
    fig.savefig(price_path, dpi=140)
    plt.close(fig)

    return BacktestVisualizationPaths(
        equity_curve=equity_path,
        drawdown=dd_path,
        price_trades=price_path,
    )


def visualization_paths_to_dict(paths: BacktestVisualizationPaths) -> dict[str, str]:
    return {
        "equity_curve": str(paths.equity_curve),
        "drawdown": str(paths.drawdown),
        "price_trades": str(paths.price_trades),
    }


def compare_visualization_paths_to_dict(paths: CompareVisualizationPaths) -> dict[str, str]:
    return {
        "strategy_ranking": str(paths.strategy_ranking),
        "equity_overlay": str(paths.equity_overlay),
        "drawdown_overlay": str(paths.drawdown_overlay),
        "asset_price": str(paths.asset_price),
    }


def render_compare_plots(
    *,
    asset_label: str,
    bars: Sequence[dict[str, Any]],
    initial_cash: float,
    ranked_rows: Sequence[dict[str, Any]],
    equity_by_strategy: dict[str, list[tuple[int, float]]],
    out_dir: Path,
) -> CompareVisualizationPaths:
    """Summary charts for a multi-strategy compare run."""
    import matplotlib.pyplot as plt

    _setup_style()
    plots_dir = visualizations_dir(out_dir)
    names = [row["strategy_id"] for row in ranked_rows]
    returns = [float(row["return_pct"]) for row in ranked_rows]
    colors = [_STRATEGY_COLORS[i % len(_STRATEGY_COLORS)] for i in range(len(names))]

    ranking_path = plots_dir / "strategy_ranking.png"
    fig, ax = plt.subplots(figsize=(9, max(3.5, len(names) * 0.55)))
    y_pos = list(range(len(names)))
    bars_h = ax.barh(y_pos, returns, color=colors, height=0.65, edgecolor="white", linewidth=0.6)
    ax.set_yticks(y_pos, labels=names, fontsize=9)
    ax.axvline(0.0, color="#64748b", linewidth=0.8)
    ax.set_xlabel("Return %")
    ax.set_title(f"{asset_label} — strategy ranking")
    ax.grid(True, axis="x", alpha=0.85)
    ax.invert_yaxis()
    for bar, value in zip(bars_h, returns, strict=True):
        ax.text(
            bar.get_width() + (0.5 if value >= 0 else -0.5),
            bar.get_y() + bar.get_height() / 2,
            f"{value:+.2f}%",
            va="center",
            ha="left" if value >= 0 else "right",
            fontsize=8,
            color="#334155",
        )
    best = ranked_rows[0]["strategy_id"] if ranked_rows else "—"
    _annotate_summary(ax, title="Best", lines=[str(best)])
    fig.tight_layout()
    fig.savefig(ranking_path, dpi=140)
    plt.close(fig)

    overlay_path = plots_dir / "equity_overlay.png"
    fig, ax = plt.subplots(figsize=(10, 4.5))
    xs = _x_values(bars, [ts for ts, _ in next(iter(equity_by_strategy.values()), [])])
    for i, sid in enumerate(names):
        curve = equity_by_strategy.get(sid, [])
        if not curve:
            continue
        eq = [e for _, e in curve]
        base = eq[0] if eq[0] else 1.0
        norm = [100.0 * e / base for e in eq]
        ax.plot(xs, norm, color=colors[i], linewidth=1.3, label=sid, alpha=0.95)
    bh = buy_hold_equity_curve(bars, initial_cash)
    if bh:
        bh_eq = [e for _, e in bh]
        base = bh_eq[0] if bh_eq[0] else 1.0
        ax.plot(
            xs, [100.0 * e / base for e in bh_eq], color="#94a3b8", linewidth=1.0, linestyle="--", label="Buy & hold"
        )
    ax.axhline(100.0, color="#cbd5e1", linewidth=0.7)
    ax.set_title(f"{asset_label} — strategy returns (indexed equity, not market price)")
    ax.set_xlabel("Bar")
    ax.set_ylabel("Indexed portfolio (start = 100)")
    ax.grid(True, axis="y", alpha=0.85)
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(overlay_path, dpi=140)
    plt.close(fig)

    dd_overlay_path = plots_dir / "drawdown_overlay.png"
    fig, ax = plt.subplots(figsize=(10, 3.8))
    for i, sid in enumerate(names):
        curve = equity_by_strategy.get(sid, [])
        if not curve:
            continue
        dd = _drawdown_series(curve)
        ax.plot(xs, [v for _, v in dd], color=colors[i], linewidth=1.0, label=sid, alpha=0.9)
    ax.set_title(f"{asset_label} — drawdown by strategy")
    ax.set_xlabel("Bar")
    ax.set_ylabel("Drawdown %")
    ax.grid(True, axis="y", alpha=0.85)
    ax.legend(loc="lower left", fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(dd_overlay_path, dpi=140)
    plt.close(fig)

    price_path = plots_dir / "asset_price.png"
    fig, ax = plt.subplots(figsize=(10, 4.2))
    closes = _plot_market_close(ax, bars, xs, linewidth=1.2, label="Close")
    ax.set_title(f"{asset_label} — market close (OHLC CSV)")
    ts_row = [int(b["timestamp"]) for b in bars]
    ax.set_xlabel(_x_axis_label(bars, ts_row))
    ax.set_ylabel(_close_price_label(bars))
    _format_price_axis(ax)
    ax.grid(True, axis="y", alpha=0.85)
    ax.legend(loc="upper left", fontsize=8)
    if closes:
        lo, hi = min(closes), max(closes)
        _annotate_summary(
            ax,
            title="Close range",
            lines=[f"min: {lo:,.2f}", f"max: {hi:,.2f}", f"last: {closes[-1]:,.2f}"],
        )
    if len(xs) > 40:
        ax.tick_params(axis="x", labelrotation=45, labelsize=7)
    fig.tight_layout()
    fig.savefig(price_path, dpi=140)
    plt.close(fig)

    return CompareVisualizationPaths(
        strategy_ranking=ranking_path,
        equity_overlay=overlay_path,
        drawdown_overlay=dd_overlay_path,
        asset_price=price_path,
    )
