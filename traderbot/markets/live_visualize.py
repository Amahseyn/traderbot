from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import requests

from traderbot.markets.market_data import fetch_ohlc_page, ohlc_rows
from traderbot.markets.registry import MarketSpec, list_supported_markets
from traderbot.markets.utils import trim_forming_candle
from utils.plots import (
    build_subplot_grid_shape,
    configure_matplotlib,
    hide_unused_subplot_axes,
    visualizations_dir,
)


@dataclass(frozen=True, slots=True)
class LiveMarketSnapshot:
    market: MarketSpec
    bars: tuple[dict[str, Any], ...]
    last_close: float
    last_timestamp: int


@dataclass(frozen=True, slots=True)
class LiveVisualizationPaths:
    dashboard: Path
    manifest: Path


def fetch_recent_bars(
    *,
    symbol: str,
    resolution: str,
    max_bars = 96,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Most recent closed candles from Nobitex UDF (one page, trimmed to max_bars)."""
    if max_bars < 1:
        return []
    known_at_unix_seconds = int(time.time())
    payload = fetch_ohlc_page(
        symbol=symbol,
        resolution=resolution,
        history_to_unix_seconds=known_at_unix_seconds,
        page=1,
        session=session,
    )
    rows = trim_forming_candle(ohlc_rows(payload, symbol=symbol, resolution=resolution))
    return rows[-max_bars:]


def fetch_all_market_snapshots(
    markets: Sequence[MarketSpec],
    *,
    resolution: str,
    max_bars: int,
    session: requests.Session | None = None,
) -> list[LiveMarketSnapshot]:
    http = session or requests.Session()
    snapshots: list[LiveMarketSnapshot] = []
    for market in markets:
        bars = fetch_recent_bars(
            symbol=market.symbol,
            resolution=resolution,
            max_bars=max_bars,
            session=http,
        )
        if not bars:
            continue
        last = bars[-1]
        snapshots.append(
            LiveMarketSnapshot(
                market=market,
                bars=tuple(bars),
                last_close=float(last["close"]),
                last_timestamp=int(last["timestamp"]),
            )
        )
        time.sleep(0.05)
    return snapshots


def snapshots_to_manifest(
    snapshots: list[LiveMarketSnapshot],
    *,
    resolution: str,
    fetched_at: int,
) -> dict[str, Any]:
    return {
        "fetched_at_utc": datetime.fromtimestamp(fetched_at, tz=timezone.utc).isoformat(),
        "resolution": resolution,
        "markets": [
            {
                "symbol": snapshot.market.symbol,
                "label": snapshot.market.label,
                "bars": len(snapshot.bars),
                "last_close": snapshot.last_close,
                "last_timestamp": snapshot.last_timestamp,
                "last_datetime_utc": datetime.fromtimestamp(
                    snapshot.last_timestamp, tz=timezone.utc
                ).isoformat(),
            }
            for snapshot in snapshots
        ],
    }


def render_live_dashboard(
    snapshots: list[LiveMarketSnapshot],
    *,
    resolution: str,
    out_dir: Path,
    show = False,
) -> LiveVisualizationPaths:
    try:
        configure_matplotlib(interactive=show)
    except ImportError as e:
        raise ImportError(
            "live market charts require matplotlib (pip install -e '.[viz]')"
        ) from e
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    plots_dir = visualizations_dir(out_dir)
    dashboard = plots_dir / f"live_markets_{resolution}.png"
    manifest_path = out_dir / "live_markets_manifest.json"

    snapshot_count = len(snapshots)
    if snapshot_count == 0:
        manifest_path.write_text(json.dumps({"markets": []}, indent=2), encoding="utf-8")
        return LiveVisualizationPaths(dashboard=dashboard, manifest=manifest_path)

    row_count, column_count = build_subplot_grid_shape(snapshot_count)
    fig, axes = plt.subplots(
        row_count,
        column_count,
        figsize=(4.2 * column_count, 3.2 * row_count),
        squeeze=False,
    )
    fetched = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    fig.suptitle(f"Nobitex live close — resolution {resolution} (as of {fetched})", fontsize=12)

    for snapshot_index, snapshot in enumerate(snapshots):
        ax = axes[snapshot_index // column_count][snapshot_index % column_count]
        closes = [float(bar["close"]) for bar in snapshot.bars]
        ax.plot(closes, color="#0072B2", linewidth=1.2)
        ax.scatter([len(closes) - 1], [closes[-1]], color="#D55E00", s=28, zorder=3)
        ax.set_title(f"{snapshot.market.label} ({snapshot.market.symbol})")
        ax.set_xlabel("bar index (oldest → newest)")
        ax.set_ylabel("close")
        ax.grid(True, alpha=0.25)
        ax.text(
            0.02,
            0.98,
            f"last: {snapshot.last_close:,.4g}",
            transform=ax.transAxes,
            va="top",
            fontsize=9,
        )

    hide_unused_subplot_axes(
        axes,
        used_count=snapshot_count,
        row_count=row_count,
        column_count=column_count,
    )

    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(dashboard, dpi=120)
    if show:
        plt.show(block=False)
    plt.close(fig)

    manifest = snapshots_to_manifest(snapshots, resolution=resolution, fetched_at=int(time.time()))
    manifest["visualization"] = str(dashboard)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return LiveVisualizationPaths(dashboard=dashboard, manifest=manifest_path)


def run_live_market_visualization(
    *,
    resolution: str,
    max_bars: int,
    out_dir: Path,
    jobs_path: Path | None,
    show: bool,
    poll_sec: float,
    max_updates: int | None,
    json_only: bool,
) -> dict[str, Any]:
    markets = list_supported_markets(jobs_path)
    session = requests.Session()
    updates = 0
    last_paths: LiveVisualizationPaths | None = None

    while True:
        snapshots = fetch_all_market_snapshots(
            markets,
            resolution=resolution,
            max_bars=max_bars,
            session=session,
        )
        fetched_at = int(time.time())
        manifest = snapshots_to_manifest(snapshots, resolution=resolution, fetched_at=fetched_at)

        if json_only:
            if poll_sec <= 0:
                return manifest
        else:
            last_paths = render_live_dashboard(
                snapshots,
                resolution=resolution,
                out_dir=out_dir,
                show=show and poll_sec > 0,
            )
            manifest = json.loads(last_paths.manifest.read_text(encoding="utf-8"))

        updates += 1
        if poll_sec <= 0 or (max_updates is not None and updates >= max_updates):
            if last_paths is not None:
                manifest["visualization"] = str(last_paths.dashboard)
                manifest["manifest"] = str(last_paths.manifest)
            return manifest

        if show:
            import matplotlib.pyplot as plt

            plt.pause(poll_sec)
        else:
            time.sleep(poll_sec)
