# Hummingbot strategy adoption (Nobitex + Hyperliquid)

Portions derived from [Hummingbot](https://github.com/hummingbot/hummingbot) (Apache-2.0); see `traderbot/third_party/NOTICES.md`.

## Per-exchange support

| Strategy | Nobitex | Hyperliquid | Notes |
|----------|---------|-------------|--------|
| **Pair trading** | Yes (spot rebalance) | Yes (perp long/short) | Z-score on aligned candles |
| **Spot grid** | Yes (spot) | Yes (on perp OHLC, paper long-only) | Set bounds from range |
| **Funding carry** | No | Yes | Public `funding_history` API |
| **Perp market making** | No | Yes (paper, maker fee tier) | Simplified PMM on bars |
| **Rule strategies** (SMA, RSI, …) | Yes | Yes | Any exported OHLC |

Fee defaults: `traderbot/markets/execution_costs.py` (Nobitex taker ~0.35%, Hyperliquid taker 0.045% / maker 0.015%).

## Evaluation

**Full matrix (recommended):** all strategies × liquid markets × six resolutions, 100 OOS windows on real data — `docs/strategy-matrix-evaluation.md`.

```bash
.venv/bin/python scripts/run_strategy_matrix_evaluation.py --samples 100 --months 6
.venv/bin/python scripts/build_strategy_eval_report.py
```

**Quick smoke:**

```bash
.venv/bin/python scripts/eval_hummingbot_strategies.py
```

Writes `results/hummingbot_eval/summary.json` with a shorter cross-check on live Hyperliquid candles.

## Lab UI

`./run-lab.sh` → **Strategies** (`/strategies`):

- Exchange selector (Nobitex / Hyperliquid)
- Fee tier (taker / maker)
- Pair, grid, and funding (HL-only) backtests

API:

- `GET /api/strategies/exchange-catalog`
- `POST /api/strategies/pair-backtest` — `exchange`, `fee_role`, `dominant_src` / `hedge_src` or CSV paths (Nobitex)
- `POST /api/strategies/grid-backtest`
- `POST /api/strategies/funding-backtest` — Hyperliquid only

No API keys or live orders; Hyperliquid uses mainnet **public** candles and funding history only.
