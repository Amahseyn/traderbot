# Crypto strategy set

All single-symbol strategies implement `Algorithm.on_bar` (long-only, one signal per closed bar)
and are registered in `traderbot/algorithms/registry.py`, so they appear in the Lab Research
strategy list, `traderbot strategy backtest|sweep --strategy <id>`, compare sessions, and tune grids
(`robust_defaults.py`, `live_tune.py`). Parameters are CLI flags (`--trend-fast-period`, …) and
fields in `default_strategy_namespace`.

Causality: every strategy only reads bars up to the current close. Swing pivots are confirmed
`swing_window_bars` bars after they print; ranges and averages use prior bars only.
`tests/test_crypto_strategies.py` checks that changing future bars never changes past signals.

## Position sizing

`Algorithm.order_size()` may return an `OrderSize` (`target_exposure` or `cash_fraction`) for
partial fills. Only `run_backtest` honors it; live traders still treat `buy`/`sell` as full
entry/exit. Sized strategies (`ma_trend`, `scalp_dip`, `dca`, `grid`) skip vectorbt metrics
(vectorbt `from_signals` assumes all-in/all-out).

| id | Existing overlap | Notes |
|----|------------------|-------|
| `ma_trend` | extends `sma_cross`/`ema_cross` | 50/200 golden cross or price-over-slow-MA entry; exit below slow MA, death cross, or trailing stop; `trend_max_adds` tranches on pullbacks to the fast MA |
| `rsi_threshold` | existing | RSI oversold/overbought mean reversion (unchanged) |
| `rsi_trend` | new | RSI crosses up through `rsi_trend_entry` above an EMA filter; exit through `rsi_trend_exit` |
| `rsi_divergence` | new | bullish divergence at confirmed swing lows + confirmation close; stop under swing low; trailing stop; bearish divergence exit |
| `range_breakout` | new (differs from `breakout_atr`) | consolidation width filter, volume confirmation, stop below breakout, measured-move target |
| `scalp_dip` | new | 1m/5m dip + green-bar bounce; fixed TP/SL; `session_end_hour_utc` flat; fixed size; cooldown after a loss |
| `dca` | new | `1/dca_order_count` of initial cash every `dca_interval_bars`; summary has `lump_sum_benchmark` |
| `grid` | new | anchored range, `grid_levels` exposure bands, shutdown on breakout (optional re-anchor) |
| `momentum_shock` | new | **proxy** for news/event momentum (price + volume shock). Plug a real feed via `EventSignalSource` |

## Multi-symbol and data-dependent strategies

- **Altcoin rotation** — `traderbot.backtesting.rotation.run_rotation_backtest(bars_by_symbol, …)`:
  holds the top-momentum symbol(s) across local CSVs. Not in the single-symbol registry/UI.
- **Cross-exchange arbitrage** — `build_cross_exchange_spreads(venue_a_bars, venue_b_bars, …)`:
  a spread screener. Needs the same asset and quote from two venues; the local data is
  Nobitex-only (`data/multisource` is a copy of `data/crypto/ohlc`), so no real result exists yet.
  A second source (e.g. Hyperliquid USDC perps vs Nobitex USDT) must be exported first.
- **On-chain analytics** — no on-chain data in the repo. Implement `EventSignalSource.score_bar`
  backed by an on-chain feed and pass it to `MomentumShockAlgorithm(event_source=…)`.
- **News/event momentum** — same interface; the shipped `PriceVolumeShockSource` is a price/volume
  proxy, not news.

## Ported / external-inspired

- **`online_logistic`** — walk-forward logistic regression on OHLCV features. Idea adapted from
  [CloddsBot](https://github.com/alsk1992/CloddsBot) `src/trading/ml-signals.ts`
  (MIT License, Copyright (c) 2026 alsk1992); rewritten in Python without orderbook/expiry features.
  Labels are applied only after `ml_horizon_bars`, so training never sees the future.
- **Pair trading** — `traderbot.backtesting.pairs.run_pairs_backtest(bars_a, bars_b, …)`:
  rolling-OLS log spread z-score. `spot_switch` (default, Nobitex spot) holds the relatively cheap
  leg; `market_neutral` simulates long/short and needs margin/futures. Original implementation
  (Martha_Stewart only describes pair trading in its README and ships no license or strategy code).
- Run-detail "Performance" tabbed chart follows the big-chart-with-tabs layout of the MIT
  Black Dashboard theme (no code copied).
