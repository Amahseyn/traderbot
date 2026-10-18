# Ensemble strategies and 1-minute workflow

## Strategy `ensemble`

Combines several child strategies on every bar. Registered as `ensemble` in Lab, CLI, and compare sessions.

| CLI flag | Values | Meaning |
|----------|--------|---------|
| `--ensemble-preset` | `1m_scalp_trend` (default), `1m_pattern_ma`, `1m_ml_trend`, `intraday_trend_stack` | Which children to run |
| `--ensemble-entry-rule` | `all`, `majority`, `primary` | When flat, when to open |
| `--ensemble-exit-rule` | `any`, `all`, `primary` | When long, when to close |

### Presets

| Preset | Children | Typical use |
|--------|----------|-------------|
| `1m_scalp_trend` | `scalp_dip` + `rsi_trend` | 1m dip buys only in an RSI uptrend |
| `1m_pattern_ma` | `chart_patterns` + `ema_cross` | Pattern break with MA confirmation |
| `1m_ml_trend` | `online_logistic` + `rsi_trend` | ML probability + trend filter |
| `intraday_trend_stack` | `rsi_trend` + `ma_trend` | Slower intraday stack (also 5m/15m) |

Entry `all` is strict (fewer trades, less noise). Exit `any` closes when any child wants out (protective).

## Recommended 1m research loop

Use **realistic fills** and fees before live (Hyperliquid perp tier 0: **0.045% taker + 0.05% slippage**, **0.015% maker** with no slippage, in `execution_costs`; Nobitex: 0.35% taker + 0.1% slippage). Research tools infer the venue from the CSV name (`*IRT` → Nobitex) when `--exchange` / `--fee` are not given:

```bash
# Export or point at your 1m CSV (e.g. BTCIRT_1.csv)
python -m cli strategy compare data/crypto/ohlc/BTCIRT_1.csv \
  --execution next_open \
  --strategy ensemble \
  --ensemble-preset 1m_scalp_trend

python -m cli strategy test data/crypto/ohlc/BTCIRT_1.csv \
  --strategy ensemble \
  --ensemble-preset 1m_scalp_trend \
  --ensemble-entry-rule all \
  --execution next_open

python -m cli strategy validate data/crypto/ohlc/BTCIRT_1.csv \
  --strategy ensemble \
  --train-fraction 0.6 \
  --validation-fraction 0.2
```

Compare several presets:

```bash
for preset in 1m_scalp_trend 1m_pattern_ma 1m_ml_trend; do
  python -m cli strategy test data/crypto/ohlc/BTCIRT_1.csv \
    --strategy ensemble --ensemble-preset "$preset" --execution next_open
done
```

## If 1m stays negative

1. Repeat the same commands on `BTCIRT_5.csv` or `BTCIRT_15.csv`.
2. Prefer presets with fewer trades (`ensemble-entry-rule all`).
3. Use Lab **custom research** with `strategy_ids: ["ensemble", "scalp_dip", "rsi_trend"]` and `execution: next_open`.
4. Keep risk limits (`capital_cap`, daily loss, kill switch) in live/paper.

See also `docs/crypto-strategies.md` and OOS tables in `docs/strategy-matrix-evaluation.md`.


## Research hygiene (walk-forward, ranking)

- `python -m cli data cache-hyperliquid BTC ETH --interval 1 --interval 5` appends closed
  candles to `data/cache/hyperliquid/*.csv`. Hyperliquid only serves ~5000 recent candles
  (~3.5 days of 1m, ~17 days of 5m), so run it daily to build multi-week history.
- `python -m cli strategy walk-forward <csv> --strategy scalp_dip --param dip_pct=0.004,0.006`
  tunes on a rolling train window and reports only out-of-sample results.
- Sweeps rank by `edge` by default: eligible (>= 30 trades), then t-stat >= 2 on per-trade
  net returns, then net average per round trip. `--rank-by return_pct` restores the old order.
- `ensemble_filter_mode=state` lets `rsi_trend` act as a trend-state filter instead of
  requiring its crossover on the same bar as the scalp entry.
