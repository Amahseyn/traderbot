# Hummingbot strategy adoption

This document summarizes what we evaluated in [Hummingbot](https://github.com/hummingbot/hummingbot) (Apache-2.0), what we ported into traderbot, and how to run the Lab UI dashboard.

## Evaluation (no live trading)

| Hummingbot area | Tested how | Verdict for Nobitex spot |
|-----------------|------------|---------------------------|
| **Stat arb / pair trading** (`controllers/generic/stat_arb.py`) | Ported spread/z-score math; traderbot `run_pair_backtest` on synthetic + CSV pairs | **Adopted** — rebalance between correlated IRT/USDT legs |
| **Grid** (`grid_strike`, grid executor simulator) | `SpotGridAlgorithm` + `run_backtest`; optional upstream pytest when `/tmp/hummingbot` is present | **Adopted (simplified)** — ranging markets only |
| **Pure / Avellaneda MM** | Upstream unit tests reviewed; not run live | **Rejected** — retail taker fees dominate |
| **Cross-exchange MM / XEMM** | Architecture review | **Rejected** — multi-venue not in scope |
| **Spot–perp arb, AMM arb** | N/A for Nobitex | **Rejected** |
| **V2 directional controllers** (Bollinger, MACD, etc.) | Overlap with existing traderbot rules strategies | **Not ported** — already covered |

Run the evaluation script (writes `results/hummingbot_eval/summary.json`):

```bash
.venv/bin/python scripts/eval_hummingbot_strategies.py
```

## Ported code and attribution

- Spread / z-score: `traderbot/algorithms/pair_trading/spread.py` (derived from Hummingbot `stat_arb.py`).
- Pair strategy: `traderbot/algorithms/strategies/pair_trading.py` + `traderbot/backtesting/pair_engine.py`.
- Spot grid: `traderbot/algorithms/strategies/spot_grid.py` (simplified from GridStrike / grid executor).
- License and notice: `traderbot/third_party/NOTICES.md`, `traderbot/third_party/hummingbot-LICENSE.txt`.

## Running backtests

**Spot grid** (single CSV, long-only):

```bash
.venv/bin/python -c "
from traderbot.algorithms.registry import algorithm_for_id
from traderbot.backtesting import run_backtest
from traderbot.utils.bars import load_bars_csv
from pathlib import Path
algo = algorithm_for_id('spot_grid', start_price=90, end_price=110, grid_count=5, take_profit_pct=0.01)
bars = load_bars_csv(Path('data/your_symbol_60.csv'))
print(run_backtest(algo, bars, fee_rate=0.001).return_pct)
"
```

**Pair trading** (two aligned CSVs):

```bash
.venv/bin/pytest tests/test_pair_trading.py -q
```

## Strategy dashboard (Lab UI)

1. Start Lab: `./run-lab.sh` (API `:8765`, UI `:3000`).
2. Open **Strategies** in the nav (`/strategies`).
3. Select dominant and hedge datasets, set lookback and z-entry threshold, run **Pair backtest**.
4. Charts show equity, spread %, and z-score (Hummingbot-style monitoring).

Pair backtest API: `POST /api/strategies/pair-backtest` with `dominant_csv`, `hedge_csv`, and optional thresholds.
