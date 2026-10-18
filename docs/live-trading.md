# Live trading operations

Paper mode is the default. **Hyperliquid perps** are the primary live venue (terminal CLI and Lab **Live** tab). Nobitex spot remains available as an optional legacy path.

## Preconditions

1. **Strategy validated** — Backtests use `next_open` execution by default; use `strategy validate` or train-window sweeps and treat holdout metrics as report-only (see `docs/lab.md`).
2. **Lab API secured** — Set `LAB_API_TOKEN` on the API host; mirror it in the UI as `NEXT_PUBLIC_LAB_API_TOKEN` (see Settings → Lab API access). Bind to `127.0.0.1` unless you intentionally expose the API on a trusted network.
3. **Hyperliquid credentials** — Wallet address + private key in `.env` on the API/terminal host (Settings → Hyperliquid). Required for live perp orders.
4. **Capital cap** — Terminal `--live-quote-budget` or risk `capital_cap` limits bot spend separately from the full wallet.

## Execution behavior (Hyperliquid — default)

| Step | Behavior |
|------|----------|
| Buy | Market open → update `BotInventory` (no exchange stop orders on HL path) |
| Sell | Market close for tracked size → then reduce inventory |
| Each bar (live) | Reconcile inventory **down** if exchange position is smaller than tracked |
| Risk | Kill switch / daily loss / drawdown block **new buys**; **sells** still allowed to flatten |
| Scope | Risk state is **per market symbol**, not one global pool |

Implementation: `HyperliquidTerminalTrader` in `traderbot/terminal/hyperliquid_trader.py`.

## Optional: Nobitex spot

Use `--exchange nobitex` (CLI) or select **Nobitex** in the Lab Live panel. Requires Nobitex API keys in Settings.

| Step | Behavior |
|------|----------|
| Buy | Market order → wait for fill → update `BotInventory` → cancel any prior stop → place stop-loss if configured |
| Sell | Cancel tracked stop (if any) → market order → wait for fill → then reduce inventory |
| Each bar (live) | Reconcile inventory **down** if wallet base is lower than tracked (e.g. stop filled off-bot) |

Implementation: `AlgorithmTrader` in `traderbot/traders/strategies/algorithm_trader.py`.

## Recommended startup sequence

```bash
# 1. Lab API (localhost + token)
export LAB_API_TOKEN="$(openssl rand -hex 24)"
./run-lab-api.sh

# 2. Lab UI (same token for browser POSTs)
# apps/lab-ui/.env.local:
# NEXT_PUBLIC_LAB_API_TOKEN=<same value as LAB_API_TOKEN>

./run-lab-ui.sh
```

Confirm **Settings → Lab API access** shows the UI token as configured and **Hyperliquid** credentials as expected.

## Terminal live (CLI)

```bash
python -m cli terminal run --exchange hyperliquid --src btc --dst usdt \
  --strategy sma_cross --interval 60 --execution live \
  --live-quote-budget 500
```

- Omit `--execution live` for paper.
- Use `--risk-kill-switch` only when you intend to block new entries (exits remain permitted).
- Nobitex spot: add `--exchange nobitex --src btc --dst rls` (or `usdt` pairs).

Lab **Live** tab runs the same stack via `POST /api/jobs/terminal-live` (requires Lab API token when auth is enabled).

## Backtest fee defaults

Shared defaults live in `traderbot/utils/trading_costs.py`: **0.045% fee** and **0.05% slippage** per taker fill (Hyperliquid perp), **0.015%** and no slippage for maker (resting limit) fills. Research tools (`sweep`, `live_tune`, `compare`, `batch`, `validation`, Lab jobs) resolve costs per venue via `resolve_cost_rates`: explicit `fee` / `slippage` win, else `exchange`, else the venue inferred from the CSV name (`*IRT` → Nobitex 0.35% taker + 0.1% slippage), else Hyperliquid. Override the Hyperliquid defaults with `TRADERBOT_DEFAULT_FEE_RATE` / `TRADERBOT_DEFAULT_SLIPPAGE_RATE`.

## Order engine (limit entries, brackets, quotes, shorts)

Strategies that return an `OrderSpec` or quotes (`perp_market_making`, `scalp_dip` with
`--scalp-order-mode bracket|maker`, or `--allow-short 1`) run through an order engine:

- **Backtest / paper:** `traderbot.backtesting.broker.SimBroker`. Limit orders fill only when a
  later bar trades *through* the price, at that price, paying the maker fee (HL 0.015%).
  Stops pay taker fee + slippage; TP/SL are measured from the actual fill; when stop and TP
  are both inside one bar the stop wins. Paper uses the same broker (next-open market fills).
- **Live Hyperliquid:** `traderbot.hyperliquid.order_manager.HyperliquidOrderManager` posts
  post-only (ALO) entries/quotes, cancels/replaces quotes every bar, and on fill places a
  reduce-only ALO take-profit plus a native reduce-only stop trigger from the fill price;
  OCO is emulated by polling. *Not yet exercised against the live exchange.*
- **Nobitex:** long-only market orders only; order-engine strategies fall back with a warning.
- Shorts are Hyperliquid perps only; `*IRT` markets are always long-only.

## Live data loop

- `--align-to-bar` (default on): wake ~1s after each bar close; retry every 2s for 20s if the
  bar is not published yet; `--poll-sec` is the maximum sleep.
- Missed bars (slow step, reconnect) are replayed oldest-first, never skipped.
- `--ws` (Hyperliquid): public candle websocket; falls back to REST when quiet for 2 bars.
- Nobitex UDF `to` is exclusive of the bar opening at `to`; the bot now asks for
  `to = start of current bar`, so the latest closed bar is no longer dropped.

## Monitoring and incident response

- Watch job logs (`/live` in the UI) and terminal JSON events for `live order failed`.
- If inventory and exchange diverge: stop the session, compare wallet/position vs bot inventory snapshot, fix manually on the exchange if needed, then restart (surplus exchange balance is **not** auto-adopted as bot inventory).
- Rotate `LAB_API_TOKEN` and exchange keys if the API was exposed without auth.

## Research vs live

| Concern | Research default | Live |
|---------|------------------|------|
| Fill timing | `next_open` | Exchange market orders at bar close signal |
| Fees / slippage | Configurable in jobs | Exchange fees + real slippage |
| Optimizer holdout | Reported, not used to pick params | N/A |

## Related docs

- Lab API and jobs: `docs/lab.md`
- UI routes: `apps/lab-ui` Settings and Live pages
