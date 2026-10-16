from __future__ import annotations

from typing import Any

from traderbot.integrations.wondertrader.live import LIVE_PROFILES, assess_live_readiness

BACKTEST_ENGINES: tuple[str, ...] = ("cta", "hft", "uft", "exec")

BACKTEST_STRATEGIES: tuple[tuple[str, str], ...] = (
    ("cta", "DualThrust"),
    ("hft", "SimpleHft"),
    ("uft", "SimpleUft"),
    ("exec", "WtMinImpactExeUnit"),
)


def capabilities_api_payload() -> dict[str, Any]:
    live = assess_live_readiness()
    return {
        "backtest": {
            "runner": "WtBtRunner",
            "engines": list(BACKTEST_ENGINES),
            "strategies": [{"mocker": m, "name": n} for m, n in BACKTEST_STRATEGIES],
            "cli": "traderbot wondertrader experiment",
            "pipeline": "wondertrader-platform",
        },
        "live": {
            "profiles": [{"id": p.id, "title": p.title, "dist_dir": p.dist_dir} for p in LIVE_PROFILES],
            "readiness": live,
        },
        "traderbot_surfaces": [
            "traderbot wondertrader check",
            "traderbot wondertrader smoke",
            "traderbot wondertrader validate [--full]",
            "traderbot wondertrader experiment [--build]",
            "traderbot wondertrader live check",
            "traderbot pipeline run wondertrader-platform",
        ],
    }
