# Changelog

All notable changes to this project are documented here.

## Unreleased

### Added

- Conda `environment.yml` (`traderbot` env, Python 3.12).
- GitHub Actions CI (pytest) on Python 3.12; weekly Chronos integration job.
- `ExecutionPolicy` for paper vs live signal handling.
- Indicator parity tests (batch ML features vs incremental strategy math).
- Streaming Bollinger updates in `traderbot/algorithms/bands.py`.
- Unified top-level `traderbot` CLI help and command dispatch.
- `traderbot interface`: complete `catalog` JSON (`command_tree`, strategies, models, pickables), plus `list`, `describe`, interactive `pick`, and `run <id>` (`traderbot/interface/`).
- `traderbot data markets` and `traderbot data live`: multi-market Nobitex UDF snapshots and dashboard PNG (`traderbot/markets/`).
- `traderbot auth`: login (session Token + TOTP), `apikeys list`/`create`, `check` for signed API key pair (`traderbot/auth/`).
- Interactive hub: bare `traderbot` / `traderbot cli` opens a prompt menu (`traderbot/interactive/`).
- Interactive **Charts & compare** menu (live charts, strategy/ML plots, ranked compare, filters).
- Modular `traderbot/terminal/` package: `catalog`, `run`, `once`, `replay` subcommands.
- `CHANGELOG.md`.
- **Cost-aware edge gate** on `sma_cross`, `ema_cross`, `rsi_threshold`, `macd_cross` and
  `bollinger_mean_reversion`: `min_edge_over_cost` (multiple of the roundtrip friction) and
  `roundtrip_cost_pct` (resolved from the CSV venue). `None` resolves to break-even (1.0) on
  1m–5m bars and off above; `0` disables it. A 1-minute roundtrip costs 0.190% on Hyperliquid
  taker / 0.900% on Nobitex while the median 1-minute candle moves 0.04–0.08%.
- `entry_order_mode` (`market` | `maker`) for those five strategies: a post-only limit entry
  pays the 0.015% maker fee with no slippage instead of 0.045% + 0.05%.
- `traderbot/algorithms/entry_orders.py` (`MakerEntry`) and
  `trading_costs.roundtrip_cost_rate` / `roundtrip_cost_pct`.
- `sma_cross` / `ema_cross` now accept `context_bars`, `buy_min_recent_return`,
  `sell_max_recent_return` and the fine-tail gates, like the mean-reversion strategies.
- `--min-edge-over-cost`, `--roundtrip-cost-pct`, `--entry-order-mode` CLI flags.

### Changed

- **1-minute threshold strategies no longer bleed their edge to fees.** On `data/ARBUSDT_1.csv`
  `macd_cross` went from -33.79% (432 fills, 216 roundtrips, 11-minute median hold) to -3.25%
  (53 fills); `sma_cross` -29.16% → -12.35%; `ema_cross` -22.05% → -3.53%. On `FILUSDT_1.csv`
  `macd_cross` -19.94% → -2.79% and `sma_cross` -14.48% → -1.96%. Cost drag, not signal
  quality, was 93–99% of those losses.
- Trend strategies default `buy_min_recent_return` / `sell_max_recent_return` to `0.0` / `0.0`
  (momentum confirmation) instead of the shared mean-reversion `-0.03` / `0.03`.
- Ad-hoc CLI output defaults to a structured **`results/<domain>/…`** tree (`runs/`, `reports/`, `visualizations/`) aligned with `solutions/`.
- Project and CI target **Python 3.12** only (`requires-python >= 3.12`; single CI job).
- `traderbot ml catalog` and `traderbot strategy catalog` accept `--implemented-only` (alias of `--implemented`).
- README clarifies `solutions/` (pipelines) vs ad-hoc `results/` output paths.
