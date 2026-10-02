# traderbot

Nobitex API client using your existing API keys ([docs-api](https://github.com/nobitex/docs-api)).

```bash
pip install -e ".[dev]"
```

`.env`:

```
NOBITEX_API_PUBLIC_KEY=   # Nobitex-Key (from panel when you created the key)
NOBITEX_API_PRIVATE_KEY=  # privateKey (saved once at creation)
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
Compare all strategies on one CSV (charts under `visualizations/` when `--out` is set):  
`traderbot strategy compare data/crypto/ohlc/BTCIRT_60.csv --out results/strategies/compare_BTCIRT_60`  
Optional recent-price filters: `--context-bars 3` (mean-reversion / MACD), `--price-confirm` (SMA/EMA). Defaults preserve indicator-only behavior.  
Use `--visualize` to force charts, `--no-visualize` (or `--no-plot`) to skip.  
Batch: `traderbot strategy batch data/crypto/ohlc --strategy ema_cross --out results/strategies`

Quick check: `traderbot` (prints profile JSON)

### OHLC → CSV (no API key; public `GET /market/udf/history`)

One market:

```bash
traderbot export --src btc --dst rls --interval D --days 90 --out data
```

Several assets and intervals — copy `export.jobs.example.json` and edit:

```bash
traderbot export --jobs export.jobs.json --out data
```

Five crypto markets, all candle intervals (writes `data/crypto/ohlc/` plus complete tail slices per forecast horizon under `data/crypto/horizons/`):

```bash
traderbot export --jobs export.jobs.5sources.json --out data/crypto
# Rebuild horizon folders from existing OHLC without re-downloading:
traderbot data horizons --from data/crypto/ohlc

traderbot ml batch data/crypto/ohlc --out results/crypto --model lightgbm --all-horizons
# Or one horizon at a time (every CSV in the folder is complete for that window):
traderbot ml batch data/crypto/horizons/4h --out results/crypto_4h --model lightgbm
pytest tests/test_multisource_data.py -q
```

Legacy flat exports under `data/multisource/` still work; run `traderbot data horizons --from data/multisource` to migrate into `data/crypto/`.

Full LightGBM grid (all exported assets × default horizons **1m, 5m, 1h, 2h, 4h, 6h, 12h, 1d** where valid):

```bash
pytest tests/test_full_matrix_lightgbm.py -q -m full_matrix
```

### Pipelines (full workflows)

```bash
traderbot pipeline list
```

| ID | What it does |
|----|----------------|
| `multisource-export` | 5 markets → `data/crypto/` (`ohlc/` + `horizons/`) |
| `lightgbm-multisource-default` | LightGBM batch, **1h** horizon per CSV |
| `lightgbm-multisource-all-horizons` | LightGBM batch, **all default horizons** + PNGs |
| `lightgbm-single-asset` | One CSV, all horizons → `results/single_asset/` |
| `chronos-single` | One CSV, Chronos eval (needs `.[chronos]`) |
| `sma-backtest` | SMA cross backtest JSON |
| `full-research-lightgbm` | Export (90d) + all-horizon LightGBM |

```bash
# Export + all horizons + visualizations (same as manual export + ml batch --all-horizons)
traderbot pipeline run full-research-lightgbm --export-days 90

# Use existing CSVs only
traderbot pipeline run lightgbm-multisource-all-horizons --data-dir data/crypto/ohlc --skip-export

traderbot pipeline run lightgbm-single-asset --csv data/crypto/ohlc/BTCIRT_60.csv
traderbot pipeline run sma-backtest --csv data/BTCIRT_D.csv --fast 5 --slow 20
```

Outputs live under **`solutions/<pipeline_slug>/`** (not loose `results/` folders):

```
solutions/lightgbm_multisource_all_horizons/
  README.md
  data/                          # OHLC CSVs (export pipelines)
  runs/BTCIRT_60/4h/
    results.json
    visualizations/*.png
  reports/
    pipeline_summary.json
    batch_manifest.json
    solution_meta.json
```

Override location: `traderbot pipeline run <id> --solutions-root . --solution-root path/to/custom`

Batch output: `results/multisource/<SYMBOL>_<INTERVAL>/` with `results.json`, `actual_vs_predicted.png`, `residuals.png`, `sample_100_usd.png` (strategy vs buy & hold from a **$100** paper account), `feature_importance.png`, plus `batch_manifest.json`. Charts and stderr include MAE/RMSE and profit vs buy & hold.

**Output paths:** `traderbot pipeline run …` writes under **`solutions/<pipeline_slug>/`**. Ad-hoc `traderbot ml batch`, `traderbot strategy compare`, and `traderbot backtest --out` use **`results/`** (or your `--out` path).

Intervals: `1`, `5`, `15`, `30`, `60`, `180`, `240`, `360`, `720`, `D`, `2D`, `3D`

```bash
pytest          # unit tests (excludes integration marker)
ruff check .    # lint (CI)
```

### ML — crypto time series (LightGBM, Chronos, …)

Optional stacks:

```bash
pip install -e ".[dev]"          # LightGBM + plots + tests (no Chronos)
pip install -e ".[chronos]"      # Amazon Chronos (PyTorch + pretrained weights)
```

**Targets:** forward log-return on `close`. Default forecast windows are **1m, 5m, 1h, 2h, 4h, 6h, 12h, 1d** (`DEFAULT_FORECAST_HORIZONS` in `traderbot/ml/intervals.py`); CLI/batch default eval uses **1h** when the candle size allows.

**Holdout (no future leakage):** features at time `t` use only bars up to `t`; train/test is a strict time split with a **horizon embargo** so training labels never depend on prices in the holdout window. Chronos predictions use only `close[:t+1]` at each holdout timestamp. See `tests/test_holdout_and_models.py`.

**Features:** OHLCV, RSI, MACD, ATR, optional `funding_rate` / `open_interest` / `volume_delta` / `market_breadth` when present on bars.

| Model | In repo | Notes |
|-------|---------|--------|
| LightGBM | yes | Tabular baseline; feature importance in results |
| Chronos | yes | Pretrained zero-shot on close |
| XGBoost | catalog | Same feature pipeline as LightGBM |
| TFT, PatchTST, TimesFM | catalog | `traderbot ml catalog` |

```bash
traderbot ml catalog
traderbot ml catalog --implemented-only
traderbot ml run data/BTCIRT_60.csv --model lightgbm --horizon-bars 4 --bar-minutes 60 --out results
traderbot ml run data/BTCIRT_60.csv --model chronos --horizon-bars 24 --bar-minutes 60 --out results
```

**Results** (per run under `--out`):

- `results.json` — metrics (`mae`, `rmse`, `directional_accuracy`)
- **Visualization** — `actual_vs_predicted.png`, `residuals.png`, and for LightGBM `feature_importance.png`

```python
from traderbot.ml import run_forecast_eval
from traderbot.ml.models import LightGBMForecastModel
from traderbot.ml.results import save_run_result
from traderbot.backtest import load_bars_csv

bars = load_bars_csv("data/BTCIRT_60.csv")
result = run_forecast_eval(bars, LightGBMForecastModel(), horizon_bars=4, bar_minutes=60)
save_run_result(result, "results/lgbm_4h")
```

Chronos integration test (downloads tiny pretrained model):

```bash
pip install -e ".[chronos,viz]"
pytest -m integration
```
