"""
Live trading readiness for WonderTrader (WtRunnerCta / Hft / Uft dist configs).

Native macOS build in this repo targets backtest (WtBtRunner). Live requires
WtRunner + broker adapters (e.g. CTP / SimNow); dist templates are validated here.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from traderbot.integrations.wondertrader.paths import wondertrader_root


@dataclass(frozen=True, slots=True)
class LiveProfile:
    id: str
    title: str
    dist_dir: str
    config_files: tuple[str, ...]


LIVE_PROFILES: tuple[LiveProfile, ...] = (
    LiveProfile(
        id="cta",
        title="CTA (WtRunnerCta)",
        dist_dir="WtRunnerCta",
        config_files=("config.yaml", "logcfg.yaml", "tdtraders.yaml", "tdparsers.yaml", "actpolicy.yaml"),
    ),
    LiveProfile(
        id="hft",
        title="HFT (WtRunnerHft)",
        dist_dir="WtRunnerHft",
        config_files=("config.yaml", "logcfg.yaml", "tdtraders.yaml", "tdparsers.yaml", "actpolicy.yaml"),
    ),
    LiveProfile(
        id="uft",
        title="UFT (WtRunnerUft)",
        dist_dir="WtRunnerUft",
        config_files=("config.yaml", "logcfg.yaml", "tdtraders.yaml", "tdparsers.yaml", "actpolicy.yaml"),
    ),
)


def _live_mode() -> str:
    mode = os.environ.get("WONDERTRADER_LIVE_MODE", "paper").strip().lower()
    if mode not in ("paper", "live", "dry-run"):
        return "paper"
    return mode


def _broker_env_configured() -> bool:
    """CTP / SimNow style credentials (set in .env for traderbot operators)."""
    keys = (
        "WONDERTRADER_BROKER_USER",
        "WONDERTRADER_BROKER_PASSWORD",
        "WONDERTRADER_BROKER_FRONT",
    )
    return all(os.environ.get(k, "").strip() for k in keys)


def assess_live_readiness(profile_id: str | None = None) -> dict[str, Any]:
    root = wondertrader_root()
    dist = root / "dist"
    mode = _live_mode()
    broker_ok = _broker_env_configured()

    profiles_out: list[dict[str, Any]] = []
    for profile in LIVE_PROFILES:
        if profile_id and profile.id != profile_id:
            continue
        pdir = dist / profile.dist_dir
        missing: list[str] = []
        present: list[str] = []
        for name in profile.config_files:
            path = pdir / name
            if path.is_file():
                present.append(name)
            else:
                missing.append(name)
        readme = (pdir / "readme.md").is_file()
        profiles_out.append(
            {
                "id": profile.id,
                "title": profile.title,
                "dist_path": str(pdir),
                "readme": readme,
                "configs_present": present,
                "configs_missing": missing,
                "configs_ok": not missing,
            }
        )

    runner_candidates = [
        dist / "WtRunnerCta" / "WtRunner.exe",
        dist / "WtRunnerHft" / "WtRunner.exe",
        root / "src" / "WtRunner",
    ]
    binary_notes = (
        "Live WtRunner is not built by macos_bt (backtest only). "
        "Build WtRunner on Windows/Linux per upstream docs, or extend macos_bt for live."
    )
    has_binary = any(p.is_file() for p in runner_candidates[:2])

    quote_factory = dist / "QuoteFactory"
    loader = dist / "LoaderRunner"

    ready_for_paper = all(p["configs_ok"] for p in profiles_out) and mode in ("paper", "dry-run")
    ready_for_live = ready_for_paper and broker_ok and has_binary and mode == "live"

    return {
        "wondertrader_root": str(root),
        "live_mode": mode,
        "broker_env_configured": broker_ok,
        "wt_runner_binary_in_dist": has_binary,
        "binary_notes": binary_notes,
        "quote_factory_dist": quote_factory.is_dir(),
        "loader_runner_dist": loader.is_dir(),
        "profiles": profiles_out,
        "ready_for_paper_config": ready_for_paper,
        "ready_for_live_trading": ready_for_live,
        "next_steps": [
            "Copy dist/WtRunner* configs to your WtRunner build output.",
            "Set WONDERTRADER_BROKER_* in .env (see docs/wondertrader.md).",
            "Run QuoteFactory + WtRunner with WONDERTRADER_LIVE_MODE=paper (SimNow).",
            "Use traderbot wondertrader backtest for regression before going live.",
        ],
    }


def load_tdtraders_template(profile_id: str = "cta") -> dict[str, Any]:
    root = wondertrader_root()
    profile = next((p for p in LIVE_PROFILES if p.id == profile_id), LIVE_PROFILES[0])
    path = root / "dist" / profile.dist_dir / "tdtraders.yaml"
    if not path.is_file():
        raise FileNotFoundError(path)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def live_capabilities_payload() -> dict[str, Any]:
    return {
        "engines": [asdict(p) for p in LIVE_PROFILES],
        "env": {
            "WONDERTRADER_LIVE_MODE": "paper | live | dry-run",
            "WONDERTRADER_BROKER_USER": "broker login",
            "WONDERTRADER_BROKER_PASSWORD": "broker password",
            "WONDERTRADER_BROKER_FRONT": "tcp:// front address",
        },
        "readiness": assess_live_readiness(),
    }
