# FinRL-Trading integration

Traderbot and [FinRL-Trading](../FinRL-Trading) (sibling repo) share credentials via `.env` and run a single **platform** workflow for Hyperliquid intraday research plus optional US equity rotation.

## Requirements

- `FinRL-Trading` cloned at `../FinRL-Trading` (or set `FINRL_TRADING_ROOT`)
- FinRL venv with `hyperliquid-python-sdk` and backtest deps
- Traderbot with `hyperliquid-python-sdk` (already in `pyproject.toml`)
- Hyperliquid: public candles need no key; wallet checks use `HYPERLIQUID_WALLET_ADDRESS` from traderbot `.env`

## Capability catalog

`GET /api/catalog/finrl-trading` — maps FinRL modules to traderbot strategies, ensemble presets, and equity runners.

`traderbot finrl run` compares **all FinRL-aligned HL strategies** by default (`finrl_ema_intraday`, `ensemble` presets, `online_logistic`, `ema_cross`, `scalp_dip`, `rsi_trend`, `macd_cross`, `breakout_atr`) using **robust defaults** and sweep DB winners when available.

Flags: `--no-strategy-compare`, `--algo-sweep` (full `validate_hyperliquid_research`), `--deploy-backtest` (FinRL `deploy.sh` adaptive rotation).

## Strategy: `finrl_ema_intraday`

Registered in the Lab catalog and CLI. Defaults: **EMA 12 / 48**, **Hyperliquid only**. Use for:

- `traderbot strategy backtest --strategy finrl_ema_intraday --csv data/.../BTCUSDT_1.csv --exchange hyperliquid`
- `traderbot terminal run --strategy finrl_ema_intraday --src btc --interval 1 --exchange hyperliquid`

Window metrics (100 bars, not annualized) come from the FinRL script; traderbot reports standard backtest `return_pct` on the same CSVs.

## Full platform run

```bash
# CLI
traderbot finrl check
traderbot finrl run --src btc --intervals 1,5 --max-bars 100

# Pipeline (Lab UI: Pipelines → "FinRL + Hyperliquid (full platform)")
traderbot pipeline run finrl-platform --src btc --max-bars 100

# Lab API
curl -X POST http://127.0.0.1:8000/api/jobs/finrl-platform \
  -H 'Content-Type: application/json' \
  -d '{"src":"btc","intervals":"1,5","max_bars":100,"equity_periods":100}'
```

Steps:

1. Export Hyperliquid OHLC into `FinRL-Trading/data/hyperliquid/`
2. Run FinRL `scripts/run_hyperliquid_intraday_experiment.py`
3. Backtest `finrl_ema_intraday` on exported CSVs (HL fees)
4. Optional: FinRL adaptive rotation report (`scripts/report_adaptive_rotation_100periods.py`)

## Catalog entry `finrl_adaptive_rotation`

Documented for US equity multi-asset rotation; run via platform pipeline step 4, not single-CSV `run_backtest`.

## Live trading

Use **paper** first: `traderbot terminal run --strategy finrl_ema_intraday --exchange hyperliquid`. Set `HYPERLIQUID_PRIVATE_KEY` for live orders. FinRL rotation remains a **research/backtest** path until wired to a broker executor.

## Causality audit (completed)

| Area | Status |
|------|--------|
| `finrl_ema_intraday` | Default `signal_style=level_lag` matches FinRL `ema_cross_signals` shift; backtests use `execution=next_open` + HL `execution_cost_profile`. |
| FinRL `intraday_engine` | Open-to-open PnL with lagged position; per-bar Sharpe in window metrics (not annualized). |
| ML `ml_strategy` | Train-only imputation; min-variance `as_of_date`; `y_return_provisional` rows excluded from supervised train/val. |
| DRL portfolio | Covariance window ends at `i-1`; model pick on validation tail with locked holdout segment (`rl_model.select_best_drl_model`). |
| Perp RL | Research scaffold: `traderbot.backtesting.perp_rl_env.PerpRlEnv` (fees/funding/slippage); serving hook `integrations/finrl_trading/policy_serve.py`. |

Validation: `python scripts/validate_finrl_platform.py` runs traderbot + FinRL static leakage checks when `FINRL_TRADING_ROOT` is set.

**Not portable to HL live:** quarterly ML, `fundamental_portfolio_drl`, adaptive rotation — US equity research only. Training new perp policies requires an external job + frozen checkpoint wired through `FrozenPolicySpec`.
