# Traderbot Lab

Lab catalogs strategy backtests and ML forecast runs in SQLite, exposes a JSON HTTP API, and ships a Next.js UI for browsing results.

## Data flow

```mermaid
flowchart LR
  CLI["traderbot CLI\nexport / backtest / ml / strategy / pipeline"]
  Disk["results/ solutions/ data/"]
  Hooks["store hooks"]
  DB["SQLite\ndata/traderbot.db"]
  API["python -m lab serve\nFastAPI JSON"]
  UI["apps/lab-ui\nNext.js"]

  CLI --> Disk
  CLI --> Hooks
  Hooks --> DB
  Disk -->|"lab sync"| DB
  DB --> API
  API --> UI
  UI -->|"GET /artifact"| API
  API --> Disk
```

1. CLI commands write artifacts under `results/`, `solutions/`, or `data/`.
2. On success, `lab.store` hooks upsert configuration snapshots and evaluation runs (disable with `TRADERBOT_STORE=0`).
3. `python -m lab sync --root results` backfills from existing `results.json` and `backtest_summary.json` files.
4. `python -m lab serve` reads the database and serves REST JSON plus safe file paths via `/artifact`.
5. `apps/lab-ui` calls the API from the browser (CORS enabled for `http://localhost:3000`).

Lab jobs (export, ML, strategy compare, pipelines) run **in-process** in the API — no `cli` subprocess.

## Environment

| Variable | Purpose |
|----------|---------|
| `TRADERBOT_STORE` | Set to `0` to disable automatic recording |
| `NEXT_PUBLIC_API_BASE` | Browser API base (default `/lab-api` — proxied to FastAPI by Next.js) |
| `LAB_API_PROXY_TARGET` | Where Next rewrites `/lab-api/*` (default `http://127.0.0.1:8765`) |
| `LAB_ALLOWED_DEV_ORIGINS` | Extra hostnames for Next `allowedDevOrigins` (comma-separated). Lab UI also allowlists local interfaces plus broad `*.*…` wildcards for LAN dev. |

Default database: `data/traderbot.db` (created by `python -m lab init`).

## Local development

One terminal (API + UI):

```bash
pip install -e ".[ui,dev]"
python -m lab sync --root results   # optional backfill
./run-lab.sh
```

`./run-lab.sh` starts the UI and ensures the Lab API on port 8765 is current: if something old is already listening, it is stopped and replaced (health must include `live_job_logs`). Start a **new** background job after restart to see streaming logs.

Two terminals:

```bash
./run-lab-api.sh
```

```bash
./run-lab-ui.sh
```

`python -m lab serve` auto-creates the SQLite schema on startup (`data/traderbot.db`).

Dev helpers: `run-lab-ui.sh` frees `LAB_UI_PORT` (default 3000) before `next dev`. Set `LAB_KILL_UI_PORT=0` to skip. API bind address defaults to `0.0.0.0` via `run-lab-api.sh` (`LAB_API_HOST`). Lab API CORS allows any origin (local research only).

Open [http://localhost:3000](http://localhost:3000). API docs: [http://127.0.0.1:8765/docs](http://127.0.0.1:8765/docs).

## Layout

- `lab/store/` — schema, upserts, queries (no HTTP).
- `lab/` — FastAPI app, CORS, artifacts, allowlisted jobs.
- `cli/` — operator CLI (`python -m cli` / `traderbot`).
- `traderbot/` — strategies, ML, pipelines, backtests, markets, live terminal.
- `apps/lab-ui/` — Next.js App Router UI only.

## UI routes

| Route | Purpose |
|-------|---------|
| `/` | Overview (research loop, stats, recent runs) |
| `/data` | Export OHLC job + download CSVs from `data/` |
| `/runs`, `/runs/[id]` | Browse runs, metrics, PNG charts, `results.json` download |
| `/configs` | Configuration snapshots |
| `/experiments` | Lab — strategy test and compare, forecast, ML batch, pipelines, compare charts. Sections: Run, Pipelines (`#pipelines`), Compare results (`#compares`) |
| `/actions` | Redirects to `/experiments` |
| `/custom` | Custom end-to-end pipeline (export, multi-dataset, compare, forecasts) |
| `/settings` | Nobitex login, API keys, profile |

## API (UI-facing)

| Method | Path | Notes |
|--------|------|--------|
| GET | `/api/stats`, `/api/runs`, `/api/runs/{id}`, `/api/configurations`, `/api/experiments`, `/api/compare-sessions`, `/api/pipelines` | Catalog |
| POST | `/api/experiments/sync` | Register `config/experiment*.json` in SQLite (no pipeline run) |
| GET | `/api/datasets` | Catalog OHLC datasets. `label` includes horizon (when the file is under `horizons/<label>/`) and the CSV start and end dates. |
| GET | `/api/datasets/{id}/download` | Download a catalog dataset file |
| GET | `/api/data/markets?scope=&q=&limit=&offset=` | Search cloned market rows in SQLite |
| POST | `/api/data/markets/sync?scope=` | Re-clone markets from Nobitex or jobs file into SQLite |
| GET | `/api/artifacts/list?out_dir=` | PNG paths under a run/solution directory |
| GET | `/artifact?path=` | Download file (`results/`, `solutions/`, `data/`) |
| GET | `/api/jobs`, `/api/jobs/{id}` | Background job status |
| POST | `/api/jobs/{id}/stop` | Stop a queued or running in-process job |
| GET | `/api/auth/status`, `/api/auth/profile`, `/api/auth/api-keys` | Nobitex credentials (`.env` on API host) |
| POST | `/api/auth/login`, `/api/auth/api-keys` | Session login / create API key (writes `.env` when requested) |
| GET | `/api/catalog/strategies`, `/api/catalog/models`, `/api/catalog/terminal` | Strategy, model, terminal catalogs |
| POST | `/api/jobs/export`, `/api/jobs/strategy-test`, `/api/jobs/strategy-compare`, `/api/jobs/pipeline-run`, `/api/jobs/pipeline-run-config`, `/api/jobs/custom-research`, `/api/jobs/terminal-once`, `/api/jobs/terminal-replay`, `/api/jobs/terminal-live` | In-process background jobs |

`GET /api/pipelines` includes `full`, `steps`, and `inputs` for the Lab Pipelines tab. Full pipelines are the end-to-end jobs. The Pipelines tab keeps Active (run forms) separate from a library where you turn pipelines on or rename the label in this browser. `POST /api/jobs/pipeline-run` takes `pipeline_id` plus those inputs (`dataset_id`, `days`, `all_assets`, `horizon`, `fast`, `slow`). Saved configs use `pipeline-run-config`, which accepts the same `params` and per-step `step_params` the form shows.

`strategy-test` and `strategy-compare` take `mode`: `strategies` (rule strategies only) or `ml` (`ml_run_id` of a finished forecast; uses that run's `holdout_forecasts.json`). `strategy-test` also requires `strategy_id`. Both jobs accept optional `cash`, `fee`, `vectorbt`, and strategy knobs (`fast`, `slow`, `signal`, `period`, `oversold`, `overbought`, `num_std`, `context_bars`, `price_confirm`, `forecast_threshold`). In `ml` mode, `ml_gated` accepts `gate_mode` and `ml_gated_base` (compare applies `ml_gated_base` to both gated rows in the ranking).

`POST /api/jobs/custom-research` runs optional `export_market_symbol` + `interval` + `export_days`, then on each selected catalog `dataset_ids` entry and/or `use_all_hourly_files` (`*_60.csv`): optional `compare_strategies` (`max_strategies`, `strategy_ids`, `cash`, `visualize`). Forecast / ML training jobs are not supported. At least one data source and `compare_strategies` is required.

Agent conventions for the UI: `.cursor/rules/lab-ui.mdc`.
