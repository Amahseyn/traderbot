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
| `ensemble` | new | Meta-strategy: preset stacks (e.g. `1m_scalp_trend` = scalp_dip + rsi_trend). See `docs/ensemble-and-1m.md` |

## Cost-aware edge gate (1-minute profitability)

Roundtrip friction is `2 × (fee + slippage)`: **0.190%** on Hyperliquid perp taker
(`0.045% + 0.05%`) and **0.900%** on Nobitex spot retail (`0.35% + 0.10%`). The median 1-minute
candle on these files moves `0.04–0.08%`, so a strategy that roundtrips every ~10 minutes pays
several times the move it is trying to capture.

`sma_cross`, `ema_cross`, `rsi_threshold`, `macd_cross` and `bollinger_mean_reversion` therefore
gate every signal on the expected move:

| knob | meaning |
|------|---------|
| `min_edge_over_cost` | required expected move as a multiple of the roundtrip cost (`1.0` = break-even, `0` = off). `None` resolves to `1.0` on 1m–5m bars and `0` above (`strategy_defaults.apply_high_frequency_edge_default`). |
| `roundtrip_cost_pct` | friction as a fraction of notional; `None` resolves from the CSV venue (`trading_costs.roundtrip_cost_pct`). |
| `entry_order_mode` | `market` (taker + slippage) or `maker` (post-only limit: `0.015%`, no slippage). Exits stay market. |

The expected move is the strategy's own target: the band/mean distance for mean reversion
(`signal_clears_cost`) and the signed recent move for trend (`trend_signal_clears_cost`).

Measured on the diagnostic files (`data/ARBUSDT_1.csv`, `data/FILUSDT_1.csv`, Hyperliquid taker
costs, market entries):

| file | strategy | before | after | fills |
|------|----------|-------:|------:|------:|
| ARBUSDT_1 | `macd_cross` | -33.79% | **-3.25%** | 432 → 53 |
| ARBUSDT_1 | `sma_cross` | -29.16% | **-12.35%** | 342 → 52 |
| ARBUSDT_1 | `ema_cross` | -22.05% | **-3.53%** | 215 → 40 |
| ARBUSDT_1 | `bollinger_mean_reversion` | -6.16% | -6.02% | 117 → 115 |
| FILUSDT_1 | `macd_cross` | -19.94% | **-2.79%** | 183 → 17 |
| FILUSDT_1 | `sma_cross` | -14.48% | **-1.96%** | 128 → 9 |

Zero-cost backtests of the same runs show why: `macd_cross` on ARBUSDT was **-0.19% gross** and
-33.79% net — 99% of the loss was friction, not signal quality. The gate removes trades whose
expected move cannot pay the fee; it does **not** create an edge. `sma_cross` on ARBUSDT is still
-12.35% net of a -7.91% gross loss, i.e. the signals themselves lose money there.

`entry_order_mode=maker` is a further, independent saving: the entry leg drops from
`0.045% + 0.05%` to `0.015% + 0`, so the gate's own threshold falls from `0.19%` to `0.11%`
(`roundtrip_cost_pct` is resolved with `maker_entry=True`) and a few more signals qualify.
Measured at the default multiple:

| file | strategy | market entry | maker entry |
|------|----------|-------------:|------------:|
| ARBUSDT_1 | `macd_cross` | -3.25% | **-1.91%** |
| ARBUSDT_1 | `sma_cross` | -12.35% | **-3.30%** |
| ARBUSDT_1 | `bollinger_mean_reversion` | -6.02% | **+0.84%** |
| FILUSDT_1 | `macd_cross` | **-2.79%** | -4.98% |
| FILUSDT_1 | `sma_cross` | **-1.96%** | -2.50% |
| FILUSDT_1 | `bollinger_mean_reversion` | **-4.71%** | -3.38% |

It helps where the strategy has an edge and hurts where it does not, because the looser
threshold admits more trades into a negative-expectancy signal. It stays opt-in for a second
reason: the Nobitex live path (`AlgorithmTrader`) ignores `order_spec`, so a maker backtest
would be optimistic there.

Coarse bars are untouched: the gate is off above 5-minute bars by default because the friction is
small relative to the bar move, and forcing it on hurt (60m `macd_cross` on ARBUSDT -1.84% →
-22.30%).

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
