# Third-party strategy sources

## Hummingbot ([hummingbot/hummingbot](https://github.com/hummingbot/hummingbot)) — Apache-2.0

We reviewed and selectively adapted ideas from:

| Hummingbot area | Traderbot adoption | Notes |
|-----------------|-------------------|--------|
| `controllers/generic/grid_strike.py` | `grid_trading` strategy | Long-only spot grid with take-profit; no leverage or executor framework |
| Pure market making / PMM | Not ported | Needs two-sided quotes and inventory skew; poor fit for Nobitex spot fees and liquidity |
| Cross-exchange / XEMM | Not ported | Nobitex is a single venue for our use case |
| `scripts/backtest_grid_strike.py` | Reference only | Full v2 backtest engine not vendored |

Original Hummingbot code is **not** copied verbatim; behavior is reimplemented against `traderbot.algorithms.base.Algorithm` and `run_backtest`.

## Martha Stewart ([lucylow/Martha_Stewart](https://github.com/lucylow/Martha_Stewart))

- **License:** No dedicated LICENSE file in the repository; README badges reference third-party templates (Bootstrap). Treat as educational / dashboard scaffolding only.
- **Trading logic:** No executable pair-trading or HFT implementation — README describes statistical arbitrage conceptually.
- **UI:** Black Dashboard + Chart.js layout inspired the Lab **Research** page (`/research`) for spread, z-score, equity, and trade markers.

## Pair trading in Traderbot

`pair_trading` uses a rolling log-spread z-score vs a **hedge** OHLC CSV (aligned timestamps). Typical Nobitex workflow: primary `eth-rls` CSV, hedge `btc-rls` CSV, Nobitex fee ~0.2% per side in backtests.

## Attribution

When extending these strategies, keep this file updated and preserve Apache-2.0 notices if copying Hummingbot source directly in the future.
