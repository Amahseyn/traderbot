# traderbot

Nobitex API client using your existing API keys ([docs-api](https://github.com/nobitex/docs-api)).

**Python 3.12** (required). Recommended: conda env from this repo:

```bash
conda env create -f environment.yml
conda activate traderbot
```

Or pip on 3.12:

```bash
pip install -e ".[dev]"
```

`.env` (see `.env.example`):

```
NOBITEX_API_PUBLIC_KEY=   # Nobitex-Key (public half of API key pair)
NOBITEX_API_PRIVATE_KEY=  # privateKey (shown once at create)
NOBITEX_AUTH_TOKEN=       # optional: session from `traderbot auth login --write-env`
```

**CLI auth** (Nobitex [API key docs](https://apidocs.nobitex.ir/api_key/api-key-guide)):

```bash
traderbot auth login --write-env          # prompts email, password, 2FA code
traderbot auth apikeys list
traderbot auth apikeys create --permissions READ --write-env   # prompts 2FA code
traderbot auth check    # verify NOBITEX_API_* (signed profile request)
```

```python
from traderbot import NobitexClient

client = NobitexClient.from_env()
client.request("GET", "/users/profile")
client.request("POST", "/market/orders/add", json_body={...})
```

### Bots & traders

| Path | Use |
|------|-----|
| `traderbot/algorithms/strategies/` | **Signal logic** (`on_bar()` → buy/sell/hold); same code for live + backtest |
| `traderbot/traders/strategies/` | **Traders** (`step()` = one loop; use `AlgorithmTrader` to run an algorithm) |
| `traderbot/bots/solutions/` | **Bot** wiring (which traders, interval) |

```python
from traderbot import Bot, NobitexTrader
from traderbot.traders import AlgorithmTrader, ExecutionPolicy


class MyTrader(NobitexTrader):
    def step(self) -> None:
        self.client.request("GET", "/market/orders/list")


Bot([MyTrader.from_env()], interval_sec=30).run()
```

See `traderbot/algorithms/strategies/`, `traderbot/traders/strategies/algorithm_trader.py`, and `traderbot/bots/solutions/example_bot.py`.

Live order hooks: override `AlgorithmTrader.on_signal` and set `execution=ExecutionPolicy.live()`. Default **paper** mode calls `on_paper_signal` instead (no API orders).

Implemented rule strategies (shared by live `AlgorithmTrader` and backtests): SMA/EMA cross, RSI thresholds, MACD cross, Bollinger mean reversion. Catalog: `traderbot strategy catalog --implemented-only`.

```python
from traderbot import algorithm_for_id, run_backtest
from traderbot.backtest import load_bars_csv

bars = load_bars_csv("data/BTCIRT_D.csv")  # from export below
algo = algorithm_for_id("sma_cross", fast=5, slow=20)
result = run_backtest(algo, bars)
print(result.return_pct)
```

CLI: `traderbot backtest data/BTCIRT_D.csv --strategy sma_cross --fast 5 --slow 20`  
Compare all strategies on one CSV (writes under `results/strategies/compare/<asset>/` when `--out` or `--visualize` is set):  
`traderbot strategy compare data/crypto/ohlc/BTCIRT_60.csv --visualize`  
Optional recent-price filters: `--context-bars 3` (mean-reversion / MACD), `--price-confirm` (SMA/EMA). Defaults preserve indicator-only behavior.  
Use `--visualize` to force charts, `--no-visualize` (or `--no-plot`) to skip.  
Batch: `traderbot strategy batch data/crypto/ohlc --strategy ema_cross` → `results/strategies/batch/<strategy>/`

Interactive CLI (recommended): run `traderbot` or `traderbot cli` in a terminal — pick a menu (**Charts & compare**, data, strategy, auth, …), then an action. Press `0` to go back or exit.

Quick check with API keys: section **Nobitex profile** in the menu, or `traderbot auth check`

Research CLI catalog (export, charts, pipelines — not live trading):

```bash
traderbot interface catalog          # full JSON: command_tree, pickables, strategies
traderbot interface list             # pickable ids (use --kind workflow --tag data)
traderbot interface describe workflow/download-crypto-1h
traderbot interface pick             # numbered menu (TTY); add --run to execute
traderbot interface run strategy/compare-btc60
traderbot interface run workflow/download-crypto-1h --dry-run
```

Terminal module (`traderbot terminal`; implementation under `traderbot/terminal/`):

```bash
traderbot terminal catalog --implemented-only
traderbot terminal once --src btc --dst rls --interval 60 --strategy sma_cross
traderbot terminal run --src btc --dst rls --interval 60 --strategy ema_cross --poll-sec 60
traderbot terminal replay data/crypto/ohlc/BTCIRT_60.csv --strategy ema_cross
```

`.env` keys are required for `run` (Nobitex client); `once`/`replay` use public UDF or CSV only. Paper mode is default (buy/sell JSON lines on stdout). `--max-steps 5` smoke-tests `run`. `--live` switches execution policy (override `on_signal` for real orders). Strategy params match `traderbot strategy` (`--fast`, `--context-bars`, …).

### OHLC → CSV (no API key; public `GET /market/udf/history`)

One market:

```bash
traderbot export --src btc --dst rls --interval D --days 90 --out data
```

Several assets and intervals — copy `export.jobs.example.json` and edit:

```bash
traderbot export --jobs export.jobs.json --out data
```

Five crypto markets, all candle intervals (writes `data/crypto/ohlc/` plus complete tail slices per horizon under `data/crypto/horizons/`):

```bash
traderbot export --jobs export.jobs.example.json --out data/crypto
# List supported markets (from export jobs JSON) and live UDF dashboard:
traderbot data markets
traderbot data live --interval 60 --bars 96   # default out: results/data/live/
traderbot data live --interval 60 --poll-sec 60   # refresh PNG every minute

# Rebuild horizon folders from existing OHLC without re-downloading:
traderbot data horizons --from data/crypto/ohlc
pytest tests/test_multisource_data.py -q
```

Legacy flat exports under `data/multisource/` still work; run `traderbot data horizons --from data/multisource` to migrate into `data/crypto/`.

### Pipelines (full workflows)

```bash
traderbot pipeline list
```

| ID | What it does |
|----|----------------|
| `crypto-jobs-export` | Crypto 1h jobs file → `data/crypto/` (`ohlc/` + `horizons/`) |
| `sma-backtest` | SMA cross backtest JSON |
| `full-research-strategies` | Export (90d) + strategy compare on hourly files |
| `crypto-1h-local` | Strategy compare on existing `*_60.csv` files |

```bash
# Export + strategy compare + visualizations on hourly files
traderbot pipeline run full-research-strategies --export-days 90

traderbot pipeline run sma-backtest --csv data/BTCIRT_D.csv --fast 5 --slow 20
```

Outputs live under **`solutions/<pipeline_slug>/`** (not loose `results/` folders):

```
solutions/full_research_strategies/
  README.md
  data/                          # OHLC CSVs (export pipelines)
  runs/compare/BTCIRT_60/…
  reports/
    pipeline_summary.json
    compare_manifest.json
    solution_meta.json
```

Override location: `traderbot pipeline run <id> --solutions-root . --solution-root path/to/custom`

Ad-hoc CLI output uses the same tree shape as pipelines, under typed folders in **`results/`**:

```
results/
  strategies/compare/<asset>/runs/<strategy_id>/…
  strategies/batch/<strategy>/runs/<csv_stem>/…
  data/live/visualizations/
```

Manifests: `reports/batch_manifest.json`, `reports/compare_manifest.json`. Per-run PNGs live in `visualizations/`. Charts and stderr include profit vs buy & hold where applicable.

**Output paths:** `traderbot pipeline run …` writes under **`solutions/<pipeline_slug>/`**. Ad-hoc commands default into **`results/<domain>/…`** (override with `--out`).

Intervals: `1`, `5`, `15`, `30`, `60`, `180`, `240`, `360`, `720`, `D`, `2D`, `3D`

```bash
pytest          # unit tests (excludes integration marker)
```

### Lab (result catalog + UI)

Browse backtests in a local Next.js UI backed by SQLite (`data/traderbot.db`).

```bash
pip install -e ".[ui,dev]"
python -m lab sync --root results    # optional backfill
./run-lab.sh                         # API + Next UI (recommended)
```

API only: `./run-lab-api.sh` (http://127.0.0.1:8765). UI only (API must already be up): `./run-lab-ui.sh`.

Architecture and env vars: [docs/lab.md](docs/lab.md).
