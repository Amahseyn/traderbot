# Live trading operations

Paper mode is the default. Use this checklist before enabling real orders (Nobitex spot or Hyperliquid perps via the terminal / Lab live jobs).

## Preconditions

1. **Strategy validated** — Backtests use `next_open` execution by default; compare sweeps on train windows and treat holdout metrics as report-only (see `docs/lab.md`).
2. **Lab API secured** — Set `LAB_API_TOKEN` on the API host; mirror it in the UI as `NEXT_PUBLIC_LAB_API_TOKEN` (see Settings → Lab API access). Bind to `127.0.0.1` unless you intentionally expose the API on a trusted network.
3. **Exchange credentials** — Hyperliquid: wallet + private key in `.env` on the API/terminal host. Nobitex: API keys and/or session token via Lab Settings or `.env`.
4. **Capital cap** — Terminal `--live-quote-budget` or risk `capital_cap` limits bot spend separately from the full wallet.

## Execution behavior (Nobitex algorithm trader)

| Step | Behavior |
|------|----------|
| Buy | Market order → wait for fill → update `BotInventory` → place stop-loss if configured (failure aborts the flow) |
| Sell | Read inventory → market order → wait for fill → then reduce inventory |
| Each bar (live) | Reconcile inventory **down** if exchange base is lower than tracked (e.g. stop filled off-bot) |
| Risk | Kill switch / daily loss / drawdown block **new buys**; **sells** still allowed to flatten |
| Scope | Risk state is **per market symbol** in the terminal, not one global pool |

Hyperliquid live uses the same inventory ordering; reconciliation reads perp position size from the exchange.

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

Confirm **Settings → Lab API access** shows the UI token as configured and exchange credentials as expected.

## Terminal live (CLI)

```bash
python -m cli terminal run --exchange hyperliquid --src btc --dst usdt \
  --strategy sma_cross --interval 60 --execution live \
  --live-quote-budget 500
```

- Omit `--execution live` for paper.
- Use `--risk-kill-switch` only when you intend to block new entries (exits remain permitted).

Lab **Live** tab runs the same stack via `POST /api/jobs/terminal-live` (requires Lab API token when auth is enabled).

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
