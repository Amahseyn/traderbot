# Agent notes

Rules: `.cursor/rules/` — **`reduce-token-usage.mdc`** and **`traderbot-core.mdc`** always apply (including **dev-mode only** for Lab, pytest, and installs); **`traderbot-naming.mdc`** on Python paths; **`lab-ui.mdc`** on `apps/lab-ui/**`; ML/strategy rules on matching globs.

**Index / ignore:** `.cursorignore` skips `data/`, `results/`, `solutions/`, CSVs, plots, Lab `node_modules/` and `.next/`. Pass explicit paths when reading run outputs.

**Docs map (do not load README for this):**

| Topic | Path |
|-------|------|
| Lab API + UI | `docs/lab.md` |
| Layout | `traderbot/` (trading), `cli/`, `auth/`, `lab/`, `nobitex/`, `markets/market_data.py`, `data/export.py` |
| Lab stack | `apps/lab-ui`, `lab/` + `lab.store`, `cli/` |

No `*_cli.py` or `backtest.py` at package root.
