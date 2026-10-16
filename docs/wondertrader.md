# WonderTrader integration

Traderbot drives the **WonderTrader** tree under `vendor/wondertrader` for:

- **Backtest** — native `WtBtRunner` (CTA / HFT / UFT / exec) on bundled CFFEX.IF sample data
- **Live readiness** — validates `dist/WtRunnerCta|Hft|Uft` templates and broker env vars (actual live needs `WtRunner` + CTP/SimNow)

## Layout

```text
traderbot/
  vendor/wondertrader/   ← local copy (not committed; run setup script)
  traderbot/integrations/wondertrader/
```

```bash
./scripts/setup_wondertrader_monorepo.sh
# optional override:
export WONDERTRADER_ROOT="$PWD/vendor/wondertrader"
```

Install Python deps:

```bash
pip install -e ".[dev,wondertrader]"
```

## macOS backtest binary

```bash
cd vendor/wondertrader
./scripts/build_macos_bt.sh
python3 scripts/prepare_sample_storage.py
```

## CLI

```bash
traderbot wondertrader check
traderbot wondertrader smoke
traderbot wondertrader validate --full          # smoke + 4 engines (needs WtBtRunner)
traderbot wondertrader experiment --build       # same as validate backtest step
traderbot wondertrader live check               # WtRunner templates + env checklist
traderbot pipeline run wondertrader-platform
```

Logs: `traderbot/logs/wondertrader/*.log`  
Artifacts: `wondertrader/experiment_results/` (manifest + per-run `runner.log`)

## Lab API

- `GET /api/catalog/wondertrader` — engines, strategies, live profiles
- `POST /api/jobs/wondertrader-platform` — body: `{ "full_backtest": true, "build_runner": false }`

## Live trading (paper / production)

Backtest in this monorepo is **macOS-native** via `macos_bt`. Live trading uses upstream **WtRunner** (not built by `macos_bt`):

1. Build `WtRunner` per WonderTrader docs (Windows/Linux typical).
2. Copy `wondertrader/dist/WtRunnerCta` (or Hft/Uft) configs into the runner output directory.
3. Set in traderbot `.env`:

```env
WONDERTRADER_LIVE_MODE=paper
WONDERTRADER_BROKER_USER=
WONDERTRADER_BROKER_PASSWORD=
WONDERTRADER_BROKER_FRONT=tcp://...
```

4. Run **QuoteFactory** + **WtRunner** with SimNow (paper) before `WONDERTRADER_LIVE_MODE=live`.

`traderbot wondertrader live check` reports missing templates and whether broker env is set.

## Tests

```bash
pytest tests/test_wondertrader_integration.py
pytest -m integration tests/test_wondertrader_integration.py::test_full_backtest_experiment
```

CI checks out upstream WonderTrader into `vendor/wondertrader` for smoke tests.
