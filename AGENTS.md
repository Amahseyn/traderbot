# Agent Notes & Project Rules

These rules apply across the entire repository for Antigravity, Cursor, and any coding agent. All agents must follow these instructions without exception.

## Docs & Layout Map

| Topic | Path |
|-------|------|
| Lab API + UI | `docs/lab.md` |
| Live trading ops | `docs/live-trading.md` |
| Architecture Layout | `traderbot/` (core trading logic), `cli/`, `auth/`, `lab/`, `hyperliquid/`, optional `nobitex/`, `markets/`, `data/export.py` |
| Lab Stack | `apps/lab-ui`, `lab/` + `lab.store`, `cli/` |
| Lab Design System | `apps/lab-ui/design-system/traderbot-lab/MASTER.md` (tokens, anti-patterns, checklist) |
| UI/UX Skill | `.agents/skills/ui-ux-pro-max/` (also `.cursor/skills/`, `.workbuddy-ai/skills/`; `python3 .agents/skills/ui-ux-pro-max/scripts/search.py "<query>" --domain ux`) |

- **No Root Scripts:** No `*_cli.py` or `backtest.py` at package root.
- **Index / Ignore:** Out of scope unless explicitly requested by the user: `data/`, `results/`, `solutions/`, CSVs, parquet, plots, Lab `node_modules/`, `.next/`, and manifests. Pass explicit paths when reading run outputs.

---

## 1. Token Usage & Tool Efficiency

- **Discovery:** Grep/find or targeted search command first. Read only files you will change, using line offset/limit (`StartLine`/`EndLine`) on sources over ~200 lines.
- **Skip wholesale reads:** Do not read `README.md` wholesale. Use `AGENTS.md` / `GEMINI.md`, `docs/*.md`, and grep for CLI or API details.
- **Minimal Diffs:** Make targeted changes. No drive-by refactoring or unnecessary extra docs. Do not re-read unchanged files.
- **Focused Tests:** Run pytest only on tests for the code touched (e.g. `.venv/bin/pytest tests/test_lab_api.py -q`). Do not run full `-m integration` or matrix runs unless requested.
- **Lab UI Verification:** Edit `apps/lab-ui/src/**` only. Verify with `./run-lab-ui.sh` or `next dev` (never `next build` / `next start` for routine agent checks).
- **Replies:** Keep responses concise and proportional to the task. Link file locations (`file.py:10-20`) instead of re-quoting large code blocks.

---

## 2. Traderbot Core Architecture & Invariants

### Bars and Causality
- `on_bar` uses only data through the current bar close (strictly no lookahead).
- At `known_at_unix_seconds`, only include bars whose close time is $\le$ that instant (`one_minute_bars_known_at`).
- For Nobitex history, set `to` to one full bar **before** `known_at_unix_seconds` (`one_minute_history_to_timestamp` for 1m; `markets.utils.history_to_timestamp` for other resolutions).

### 1m OHLC Entry Points
- **CSV:** `one_minute_csv_for_coarse`, `load_one_minute_bars` (`data/intrahour.py`).
- **Live API:** `fetch_one_minute_bars` (`markets/market_data.py`).
- **Export:** `data/export.py`; Lab job `lab/tasks.py`. Signing: `nobitex/client.py`, `nobitex/signing.py`.
- **Helpers:** `one_minute_history_to_timestamp`, `one_minute_bars_known_at` (`utils/bars.py`).
- **Invariance:** Do not duplicate 1m load/fetch in CLI, batch, or pipelines.

### Shared Helpers (`utils`)
- **Domain-agnostic helpers:** Top-level `utils/` (series lookups, matplotlib layout). Import from the defining module.
- **Trading-domain helpers:** `traderbot/utils/` — import from the defining module; small re-export set on `traderbot.utils` only.
- **Package-local duplicates:** `{package}/utils.py` (`markets/utils.py`, `terminal/utils.py`); keep orchestration in named modules.
- **Facades:** `traderbot/utils/algorithms.py` with thin re-exports at `traderbot.algorithms.utils`.

### Indicator Reuse & Imports
- Reuse existing indicators: `algorithms/bands.py`, `algorithms/streaming.py`.
- Lab entry: `python -m lab` (`serve`, `init`, `sync`) or `./run-lab-api.sh`. CLI: `python -m cli`.
- Register new strategies in `algorithms/registry.py`.
- Backtesting: `from traderbot.backtesting import …` only. Keep `traderbot/__init__.py` minimal.
- Module-level imports only (lazy imports only for cycles or optional extras e.g. `matplotlib`).

---

## 3. Python Naming, Types, and Style Conventions

### Functions and Methods
- `snake_case` only; public names are **verb + object** so call sites read like natural English.
- **Load from disk:** `load_*` (e.g. `load_bars_csv`, `load_one_minute_bars`).
- **Fetch over HTTP:** `fetch_*` (e.g. `fetch_one_minute_bars`, `fetch_latest_closed_bar`, `fetch_ohlc_page`).
- **Pure transforms:** `build_*`, `attach_*`, `enrich_*`, `normalize_*`.
- **Orchestration:** `run_*` (CLI handlers, pipelines, backtests).
- **Resolve paths / metadata:** Noun phrase (`one_minute_csv_for_coarse`, `market_symbol`).
- **Time $\rightarrow$ API query:** `*_history_to_timestamp` (Nobitex `to` parameter); never expose `udf` in public names.
- **Filter bar lists for causality:** `*_bars_known_at` with a full time parameter.
- **Private helpers:** Leading `_` only for helpers private to one module; do not import `_`-prefixed symbols elsewhere.
- **No synonyms:** One canonical function per behavior (`fine_bars_for_coarse`, `as_of_*`, etc. are disallowed).

### Variables (Parameters, Loops, Locals)
- `snake_case`, full words — never `tmp`, `val`, `res`, `ts`, `t`, `df` (except real `pandas.DataFrame` named `dataframe` or `features_frame`).
- **Plural sequences:** `bars`, `closes`, `one_minute_bars`, `jobs`. **Singular:** `bar`, `job`, `payload`.
- **Counts:** `bar_count`, `max_bars`, `horizon_bars` — always include unit in name (`*_bars`, `*_minutes`, `*_seconds`).
- **Booleans:** Read as a question — `auto_load`, `render_plots`, `skip_export` (not `flag`, `ok`, `done`).
- **Time:** POSIX ints $\rightarrow$ `*_unix_seconds`. Bar length $\rightarrow$ `bar_minutes`, `coarse_minutes`. Do not use `as_of` / `timestamp` as decision-time variable names (`timestamp` is the bar dict key only).
- **Paths:** `*_path` for `Path`; `*_csv` when always a CSV path.
- **Market:** `symbol`, `resolution`; bar dict keys stay `open`, `high`, `low`, `close`, `volume`, `timestamp`.
- **Loops:** `for bar in bars:` — not `b`, `row`, `x`. Loop index: `bar_index`, not bare `i`/`j` outside tiny numeric loops.

### Constants, Types, Collections & Magic Numbers
- Module constants: `SCREAMING_SNAKE`; shared durations in `traderbot/utils/constants.py` — import, do not copy.
- Omit redundant scalar type annotations on literal constants and obvious parameter defaults.
- Never construct with `list[int](…)` / `tuple[str, …](…)` — use `list(…)`, `[]`, `tuple(…)`.
- Registries at import: `tuple[Entry, …]`; runtime lists from helpers: `list[…]`.
- Domain literals (bar windows, timeouts, page sizes, default cash) $\rightarrow$ named constant or parameter. Bare `0`, `1`, `-1` allowed only for obvious control flow or small assert-only test integers.
- **Vocabulary:** 1m loaders/fetchers $\rightarrow$ `one_minute_*`. Intrahour columns $\rightarrow$ `fine_return_*`. Coarse CSV $\rightarrow$ `{symbol}_{resolution}.csv`; 1m sibling $\rightarrow$ `{symbol}_1.csv`.

---

## 4. Traderbot Lab Next.js UI Conventions (`apps/lab-ui/**`)

### Scope & Structure
- Next.js App Router only under `apps/lab-ui/src/`. Do not edit `.next/`, `node_modules/`, or build output.
- **Pages:** `src/app/**/page.tsx`
- **Shared UI:** `src/components/ui/*`, `JobMonitor`, `ArtifactGallery`, `Nav`
- **API Client:** `src/lib/api.ts`, `src/lib/format.ts`
- Browser calls Lab API via `NEXT_PUBLIC_API_BASE` (default `/lab-api`, proxied to FastAPI).

### Pages Map
- **Overview (`/`):** Research loop cards, stats, recent runs.
- **Data (`/data`):** Optional Nobitex export + browse/download CSVs under `data/` (`GET /api/data/csv-files`, `GET /artifact`).
- **Lab (`/experiments`):** Strategy test and compare, saved pipelines, compare charts (`/actions` redirects here).
- **New (`/new`):** Opportunity discovery (HL universe or catalog), job monitor, past discovery runs; links to Custom.
- **Custom (`/custom`):** Configure full pipeline: optional export, multi-dataset, strategy compare, multi-model forecasts (`POST /api/jobs/custom-research`).
- **Optimizer (`/optimizer`):** Optuna/grid sweeps, batch Optuna on catalog CSVs, HL market research pipelines, stored params, sweep history (`POST /api/jobs/strategy-sweep`, `custom-research`, `pipeline-run`).
- **Live (`/live`):** Hyperliquid-first paper/live (`POST /api/jobs/terminal-once`, `terminal-live`); Nobitex spot optional.
- **Strategies (`/strategies`):** Ephemeral pair/grid/funding paper backtests (`POST /api/strategies/*`); venue matrix from `GET /api/strategies/exchange-catalog`.
- **Settings (`/settings`):** Lab API token, Hyperliquid credentials, optional Nobitex (`/api/auth/*`).
- **Research loop:** Nav plus overview cards (`WorkflowCards`, `lib/workflow.ts`): Data $\rightarrow$ Lab $\rightarrow$ Runs. Do not add a second bar of the same links.
- **Runs / Configurations:** Read-only catalog views.

### UI & Error Handling Conventions
- **Lab API Errors:** `fetchJson` in `api.ts` parses JSON `error` / `detail`. Use `ErrorState` for query failures and `JobErrorAlert` for mutation/job POST errors (both show a Settings link on 401). `LabAuthBanner` in root layout warns when `LAB_API_TOKEN` is set but `NEXT_PUBLIC_LAB_API_TOKEN` is missing.
- **Component tokens:** Use tokens from `tailwind.config.ts` (`surface`, `panel`, `border`, `accent`, `muted`) and `table.data` / `badge-*` in `globals.css`. Prefer shared `Card`, `Button`, `Field`, `PageHeader`, `JobMonitor` over one-off styling.
- **Artifact paths:** Use `artifactUrl` / `artifactDownloadUrl`; normalize absolute paths with `normalizeArtifactPath`.
- **Job polling:** React Query (`refetchInterval` while `queued` or `running`); invalidate `runs`, `stats`, `experiments`, `data-csv` on completion.
- **Backend Pairing:** Extend `lab/` (FastAPI) and document in `docs/lab.md` when UI requires new data. Never call CLI from browser.

### Design System (Strictly Enforced)
Source of truth: `apps/lab-ui/design-system/traderbot-lab/MASTER.md`. Guidance skill: `.agents/skills/ui-ux-pro-max/` (also mirrored at `.cursor/skills/` and `.workbuddy-ai/skills/`).
- **Tokens Only:** Style with `surface` / `panel` / `panel-elevated` / `border` / `border-bright` / `accent` / `on-accent` / `muted` declared in `globals.css`. No raw hex colors in components.
- **Semantic Colors:** Accent is for interaction only. Red and green are strictly reserved for PnL and status; never use them as decoration.
- **No AI-Slop Decoration:** No gradient backgrounds, gradient text, glow shadows, decorative `backdrop-blur`, ambient `blur-3xl` blobs, or hover lift/scale on cards and buttons.
- **Contrast & Motion:** Normal text contrast $\ge$ 4.5:1. Primary buttons use `text-on-accent` on `bg-accent`. 150ms transitions, no infinite animations, `prefers-reduced-motion` respected globally.
- **Data Display:** Numeric columns use `tabular-nums`. Status must never rely on colour alone.

---

## 5. Strategy Signals & Recent-Price Context (`traderbot/algorithms/**/*.py`)

- **Context Rule:** Strategy signals must respect recent price path, not blind thresholds. Never fire on a single indicator level alone.
- **Cost-Aware Edge Gate:**
  - Roundtrip friction: `0.190%` on Hyperliquid perp taker, `0.900%` on Nobitex spot retail. Median 1m candle moves `0.04–0.08%`. Any signal whose expected move is smaller than friction is a guaranteed loss.
  - `min_edge_over_cost`: Expected move as multiple of roundtrip cost. `1.0` is break-even; `0` disables. Default `None` resolves via `strategy_defaults.apply_high_frequency_edge_default`: **1.0 on 1m–5m bars, 0 above**.
  - `roundtrip_cost_pct`: Resolved from CSV venue via `trading_costs.roundtrip_cost_pct`; `0` disables.
  - Expected move calculation: Mean reversion uses distance to reversion target (band mean for `bollinger_mean_reversion`, `period`-bar mean for `rsi_threshold`) via `signal_clears_cost`; trend uses signed recent move over `context_bars` via `trend_signal_clears_cost`.
  - MACD reuses `apply_mean_reversion_context` for direction gate; edge comes from `recent_cumulative_return`.
- **Mean Reversion (`rsi_threshold`, `bollinger_mean_reversion`):**
  - Return over $k$ bars via `traderbot/algorithms/price_context.py`.
  - Defaults: `context_bars=0` for legacy behavior. When enabled, `buy_min_recent_return` / `sell_max_recent_return` avoid fading sharp recent moves.
  - Wire knobs through `registry.py` `_KWARGS_FROM_ARGS` and `strategy_cli.py`.
- **Trend (`sma_cross`, `ema_cross`):**
  - Optional `price_confirm`: require close on trend side of fast average before `buy`/`sell`.
  - Optional `context_bars` + `buy_min_recent_return` / `sell_max_recent_return`: take `0.0` / `0.0` for trend (`strategy_defaults.apply_strategy_baseline_defaults` rewrites shared `-0.03`/`0.03`).
- **Entry Execution (Maker vs Taker):**
  - `entry_order_mode` (`market` | `maker`), `entry_offset_pct`, `entry_ttl_bars` via `traderbot/algorithms/entry_orders.py::MakerEntry`. Maker entries rest post-only (pays 0.015% no slippage vs 0.095%).
  - **Entries only:** `sell` closes risk and stays market order (unfilled exit is worse than fee). `market` stays default to match live fill expectations.
- **Validation:**
  - Tests: `tests/test_strategies.py`, `tests/test_price_context.py`, `tests/test_trading_costs.py`.
  - `min_edge_over_cost`, `roundtrip_cost_pct`, and `entry_order_mode` excluded from `registry.strategy_param_names`; `entry_offset_pct` / `entry_ttl_bars` excluded for threshold strategies.

---

## 6. Development Mode & Environment Setup (Always)

- **Local Dev Always:** Run and verify in local dev unless explicitly asked for production builds or release packaging.
- **Python Virtualenv:** Always use `.venv/bin/pytest` and `.venv/bin/python -m lab`. Do not install packages into system Python (PEP 668).
  ```bash
  # Setup & dependencies
  python3 -m venv .venv
  .venv/bin/pip install -e ".[ui,dev,backtest]" "httpx2"
  .venv/bin/python -m lab init
  ```
  *(Note: `python -m lab init` creates `data/traderbot.db` with `sweep_sessions` table; required to avoid `sqlite3.OperationalError` in strategy compare and terminal tests).*
- **Running Lab:**
  - Complete Lab (API + UI): `./run-lab.sh` (API port 8765, UI port 3000, UI proxies `/lab-api`).
  - Lab API only: `./run-lab-api.sh` or `.venv/bin/python -m lab serve` (reload mode, jobs run in-process).
  - Lab UI only: `./run-lab-ui.sh` (`next dev` on port 3000).
- **Background Processes:** Use repo `run-*.sh` scripts and execute long-running services in the background.
- **Credentials:**
  - Optional for local Lab (overview, experiment sync, strategy catalog).
  - Live orders require `NOBITEX_*` or Hyperliquid credentials in `.env`.
