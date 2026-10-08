# Agent notes

Rules: `.cursor/rules/` — **`reduce-token-usage.mdc`** and **`traderbot-core.mdc`** always apply (including **dev-mode only** for Lab, pytest, and installs); **`traderbot-naming.mdc`** on Python paths; **`lab-ui.mdc`** on `apps/lab-ui/**`; strategy rules on matching globs.

**Index / ignore:** `.cursorignore` skips `data/`, `results/`, `solutions/`, CSVs, plots, Lab `node_modules/` and `.next/`. Pass explicit paths when reading run outputs.

**Docs map (do not load README for this):**

| Topic | Path |
|-------|------|
| Lab API + UI | `docs/lab.md` |
| Layout | `traderbot/` (trading), `cli/`, `auth/`, `lab/`, `nobitex/`, `markets/market_data.py`, `data/export.py` |
| Lab stack | `apps/lab-ui`, `lab/` + `lab.store`, `cli/` |

No `*_cli.py` or `backtest.py` at package root.

## Cursor Cloud

- Install `python3.12-venv` before `python3 -m venv .venv`. Use `.venv/bin/pytest` and `.venv/bin/python -m lab`.
- Dev extras: `pip install -e ".[ui,dev,backtest]" "httpx2"`, then `python -m lab init`. Current Starlette's test client imports `httpx2`. `lab init` creates `data/traderbot.db` with `sweep_sessions`; without that schema, strategy compare and terminal tests raise `sqlite3.OperationalError`.
- Lab: `./run-lab.sh` (API port 8765, UI port 3000). UI calls the API through `/lab-api`.
- Nobitex credentials are optional for local Lab (overview, experiment sync, strategy catalog). Live orders need `NOBITEX_*` in `.env`.
