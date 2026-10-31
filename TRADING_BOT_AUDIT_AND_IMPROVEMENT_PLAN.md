# Trading Bot Repository Audit and Improvement Plan

**Repository:** [Amahseyn/traderbot](https://github.com/Amahseyn/traderbot)  
**Audit snapshot:** 2026-10-28, default branch `main`, commit `00134f8cede72822cc23c4dbd40f1b0935ef974c`  
**Scope:** Static source/documentation/test review through GitHub repository APIs. No live orders, deployment, or strategy changes were made.

> **Evidence labels**
> - **Verified:** directly supported by repository source or documentation.
> - **Risk / hypothesis:** plausible failure mode that requires targeted execution or data tests to confirm.
> - **Not established:** cannot be concluded without running the suite, inspecting real fills, or obtaining representative market data.

## 1. Executive summary

This is a broad research and trading codebase, not just a single strategy. It has a shared algorithm interface, multiple strategy families, a backtest broker, parameter optimization and walk-forward tools, risk management, and separate live execution paths for Hyperliquid perpetuals and Nobitex spot.

The most important improvements are not adding more indicators. They are closing the gap between backtest assumptions and live execution, enforcing centralized risk and position sizing consistently, reconciling exchange state after every order lifecycle event, and requiring evidence of net edge on untouched data before live deployment.

### Highest-priority conclusions

1. **P0 — Reconcile live execution with strategy and backtest semantics.** `traderbot/algorithms/base.py` explicitly says partial `OrderSize` sizing is honored by the backtest engine but live traders treat signals as full entries/exits. That is a material parity gap for strategies that rely on partial sizing. Test each strategy/venue combination and either implement identical sizing semantics or reject unsupported combinations.
2. **P0 — Make protective-order health a hard safety invariant.** `docs/live-trading.md` says the default Hyperliquid market path has no exchange stop orders, and says the order-engine live path has not yet been exercised against the live exchange. In `traderbot/hyperliquid/order_manager.py`, stop placement errors are emitted as events; verify the caller immediately blocks new risk, flattens or otherwise applies a defined fallback when protection is required but absent.
3. **P0 — Define risk scope across the account, not only per symbol.** `docs/live-trading.md` explicitly documents that risk state is per market symbol. Multiple symbols can therefore each consume their own daily-loss/drawdown budget unless a separate portfolio-level guard exists. Add account-level notional, margin, correlated exposure, and aggregate loss limits.
4. **P1 — Treat reported backtest returns as conditional on fill assumptions.** `traderbot/backtesting/engine.py` supports `close` execution and documents it as optimistic; use `next_open` or a validated order-aware fill model for selection. The OHLC order broker's deterministic stop-first rule is conservative in one ambiguous case, but OHLC bars still cannot establish intrabar event ordering or queue position.
5. **P1 — Make every strategy's economics cost-aware.** `scalp_dip` uses short holding periods and small targets; the strategy module documents that a recent 5m preset lost less out of sample than legacy settings but was not profitable. At the documented Hyperliquid taker assumptions, a market round trip costs approximately 0.19% before funding and other impact; small gross edges can be overwhelmed by costs.
6. **P1 — Preserve strict temporal separation in optimization.** The repository has walk-forward, validation, and optimized-parameter temporal guards. Keep these as mandatory paths, audit fallback behavior for missing timestamps, and make selection criteria robust to multiple testing and uncertainty.
7. **P2 — Improve operational evidence.** Add a per-order lifecycle ledger, strategy/market cost attribution, live-versus-backtest slippage reports, and alerts for stale data, unprotected positions, partial fills, and exchange/inventory divergence.

No return, Sharpe, drawdown, or win-rate figure is asserted here because no canonical run results or real fill ledger were provided as part of this static audit.

## 2. Repository map and trade lifecycle

### Main components

| Component | Relevant paths | Responsibility |
|---|---|---|
| Strategy contract and registry | `traderbot/algorithms/base.py`, `registry.py`, `strategies/` | Bar-by-bar signals, order specifications, quotes, strategy catalogue |
| Indicator/context helpers | `traderbot/algorithms/streaming.py`, `price_context.py`, `warmup.py`, `traderbot/utils/indicators.py` | Streaming indicator state, warm-up and price context |
| Backtesting | `traderbot/backtesting/engine.py`, `broker.py`, `fills.py` | Signal timing, simulated orders, fees/slippage, equity and trade records |
| Validation/optimization | `backtesting/walk_forward.py`, `validation.py`, `sweep.py`, `optimized_params.py` | Parameter search, chronological validation, stored parameter retrieval |
| Risk | `traderbot/risk/manager.py`, `runtime.py`, `validation.py` | Entry gating, daily loss, drawdown and kill-switch logic |
| Hyperliquid live | `traderbot/terminal/hyperliquid_trader.py`, `traderbot/hyperliquid/order_manager.py` | Perp orders, positions, bracket orders, market data |
| Nobitex live | `traderbot/traders/strategies/algorithm_trader.py`, `traders/inventory_reconcile.py` | Spot orders, fill waiting, stop handling and wallet reconciliation |
| Data | `traderbot/data/export.py`, `bar_cache.py`, `crypto_store.py`, `markets/` | OHLC collection, caching, symbol/timeframe data |
| Terminal/paper | `traderbot/terminal/`, `paper_portfolio.py` | Session orchestration, replay and paper portfolio |
| Research UI / persistence | `lab/`, `apps/lab-ui/`, `traderbot/pipelines/` | Experiment execution, results browsing and job workflows |
| Tests | `tests/test_*.py` | Unit, integration, execution, risk and research regression coverage |

### Trade lifecycle to verify end to end

1. Resolve venue, symbol, timeframe and credentials/configuration.
2. Load closed candles and verify timestamp ordering, gaps, duplicates and freshness.
3. Update the strategy state with one completed bar; compute a signal/order specification.
4. Apply risk checks and venue capability constraints.
5. Calculate order size and round to venue precision/minimums.
6. Submit or simulate the order; record requested size, order ID, status and fills.
7. Attach or update stop/TP orders where applicable; verify their exchange-side status.
8. Reconcile actual exchange position, open orders and internal inventory.
9. Mark equity using account equity and unrealized PnL without double counting.
10. Persist the complete event and calculate net realized/unrealized PnL including fees, slippage, funding and other applicable costs.

The static review cannot confirm all these steps behave correctly under partial fills, network timeouts, process restarts, and real exchange responses. These scenarios require fault-injection tests and a small, controlled exchange test environment.

## 3. Strategy-by-strategy assessment

The repository contains more strategies than can be judged from their names alone. The following is a source-level classification and test plan, not a claim that any strategy has a profitable edge.

| Strategy / family | Source | Initial assessment | Recommendation |
|---|---|---|---|
| SMA/EMA cross, MA trend | `strategies/sma_cross.py`, `ema_cross.py`, `ma_trend.py` | Trend-following; prone to whipsaws in ranges and lag at reversals. Moving averages are highly correlated evidence. | Retain as baselines. Test fewer, interpretable filters; evaluate net returns by regime and turnover. |
| MACD, RSI, RSI trend/divergence | `macd.py`, `rsi.py`, `rsi_trend.py`, `rsi_divergence.py` | Momentum/mean-reversion signals can conflict. RSI divergence can be subjective/noisy and parameter-sensitive. | Retain for controlled comparison; don't stack correlated oscillators without incremental out-of-sample evidence. |
| Bollinger mean reversion | `bollinger.py` | Depends on stable range/mean reversion; can accumulate losses in persistent trends. | Require regime/trend guard hypothesis and explicit risk limits; test tail events. |
| ATR breakout | `breakout_atr.py` | Breakout logic excludes the current bar from prior highs/lows, which avoids using the current high as its own prior range. Entry threshold uses current ATR; exit uses a range-break rule and a stop flag. | Retain as a trend hypothesis. Test gap-through-stop fills, stop execution timing, and parameter stability. |
| Scalp dip | `scalp_dip.py` | Frequent, small targets are sensitive to spread, fees, slippage, missed fills and bar-resolution ambiguity. The code comments explicitly warn the cited 5m preset was not profitable OOS. | Do not promote based on win rate. Keep disabled for live use until net edge is robust after realistic costs and live paper tracking. |
| Ensemble | `ensemble.py` | Voting/filtering may reduce false signals, but correlated children can create false confidence and additional state-sync complexity. | Test each child and the ensemble on identical folds; compare incremental net expectancy and turnover, not only return. |
| Grid / spot grid / DCA | `grid.py`, `spot_grid.py`, `dca.py` | Can disguise inventory accumulation and trend risk as frequent realized gains. Grid assumptions depend on range persistence, inventory caps and capital availability. | Keep paper-only until exposure caps, stress scenarios, trend exits and worst-case inventory are demonstrated. |
| Perp market making | `perp_market_making.py` | Profit depends on adverse selection, queue position, maker fill probability, inventory skew and fee tier. OHLC-only backtests cannot model queue priority. | Experimental until order-book/replay and live-fill data calibrate fill probability and adverse selection. |
| Pair trading | `pair_trading.py`, `pair_trading/spread.py` | Spread stationarity, hedge ratio stability and synchronized data are prerequisites. Legging and transaction costs can dominate. | Require rolling cointegration/stability tests, synchronized bars, hedge sizing, and legging-risk controls. |
| Funding carry | `funding_carry.py` | Funding estimates can change; price basis, fees, liquidation/margin and funding timing matter. | Keep separate from directional signal tests; include realized funding and basis convergence/expansion in PnL. |
| Online logistic / FinRL | `online_logistic.py`, `finrl_ema_intraday.py`, `finrl_trading/` | Greater data/validation burden; non-stationarity and reward leakage are risks. | Experimental. Compare against simple baselines with strict temporal splits and fixed training protocols. |
| Momentum shock, range breakout, chart patterns | `momentum_shock.py`, `range_breakout.py`, `chart_patterns.py`, `patterns/` | Event/pattern signals may be sparse and sensitive to definitions and sample selection. | Require adequate event count and predeclared rules; avoid tuning to a handful of examples. |

### Strategy design rules

- Every strategy must define whether signals are generated only from fully closed bars.
- The same signal and sizing semantics must apply in backtest, paper and live, or unsupported behavior must fail closed.
- Separate **signal quality** from **execution quality**. A good signal may lose through spread/impact; a profitable simulated fill model may hide a weak signal.
- Use a small number of hypotheses. Each new filter should have an ablation experiment proving incremental benefit.
- Evaluate performance by market regime, asset, timeframe, long/short side, and cost scenario. Avoid pooling away a strategy's failure modes.
- Strategy state must be reset deterministically and synchronized with actual position state after reconnect/restart.

## 4. Critical correctness and financial safety findings

| ID / priority | Finding and evidence | Impact | Proposed change and validation |
|---|---|---|---|
| A-01 / **P0** | **Live sizing parity gap.** `traderbot/algorithms/base.py` documents that backtests honor partial `OrderSize` but live traders treat every buy/sell as a full entry/exit. | Live exposure may differ materially from backtest exposure; sizing-dependent metrics are not portable to live. | Implement a shared sizing contract for each venue, or reject partial-size strategies in live mode. Add parity tests for partial entries/exits, shorts, precision, minimum order and equity changes. |
| A-02 / **P0** | **Protective order reliability needs a fail-safe.** `docs/live-trading.md` says the default Hyperliquid market path has no exchange stop orders; `order_manager.py` emits bracket placement errors. | An open leveraged position may remain unprotected after an API or validation failure. | If strategy/config requires a stop, verify stop acknowledgment and size/trigger after entry; if absent, block new entries and invoke an explicit emergency policy. Fault-inject stop-placement failures and partial fills. |
| A-03 / **P0** | **Risk is documented as per symbol.** `docs/live-trading.md` states risk state is per market symbol, not one global pool. | Simultaneous symbols can exceed aggregate drawdown, notional or correlated exposure limits. | Add account-level risk manager: total gross/net notional, margin utilization, daily loss, peak-to-trough drawdown, max concurrent positions and correlated group caps. Test multi-symbol loss scenarios. |
| A-04 / **P0** | **Exchange/inventory reconciliation is asymmetric.** Docs describe reconciliation down when exchange holdings are smaller; surplus exchange balance is not auto-adopted. | Safe in some cases but can leave unexplained positions, orphaned orders or mismatch after restart. | Make mismatch a first-class halted state: reconcile positions and open orders, distinguish bot-owned vs external holdings, require explicit adoption/flatten policy, and test restart with filled stop/TP and partial order. |
| A-05 / **P0** | **Live order-engine path is documented as not yet exercised against the live exchange.** `docs/live-trading.md`. | Simulation assumptions and API lifecycle may not match venue behavior; bracket/OCO bugs could be costly. | Use testnet or minimum-size controlled validation with no strategy promotion until order-state machine, cancel/replace, partial fills, stop trigger, reduce-only, reconnect and duplicate submission are verified. |
| A-06 / **P1** | **Backtest close-fill mode is explicitly optimistic.** `traderbot/backtesting/engine.py` documents `execution="close"` as optimistic. | Signals may use close information and fill at that same close, overstating achievable entry/exit prices. | Use `next_open` as a default for close-derived signals; keep close mode for diagnostics only. Add tests that strategy sees no future bars and fills only after signal availability. |
| A-07 / **P1** | **OHLC cannot model true order-book execution.** `traderbot/backtesting/broker.py` fills limit orders when later bars trade through the limit; this cannot establish queue priority, partial fill likelihood or adverse selection. | Maker strategies and limit orders may look more profitable than live reality. | Add conservative fill assumptions and replay/book data where available; measure live-vs-sim fill rate, realized spread and markout. |
| A-08 / **P1** | **Parameter fallback can permit records with missing optimization timestamps.** `traderbot/algorithms/optimized_params.py` allows legacy records without `optimize_end_utc` when temporal metadata is missing. | A parameter set may be selected without proving it predates evaluation data. | For deployment/holdout selection, fail closed on missing temporal provenance; allow legacy fallback only in an explicitly marked exploratory mode. Test missing, malformed and overlapping timestamps. |
| A-09 / **P1** | **Strategy-level risk settings must be mapped to actual account risk.** `RiskLimits` includes daily loss, drawdown, kill switch and stop-loss; the live docs say risk blocks new buys while sells remain allowed. | Blocking new buys is not equivalent to flattening risky existing positions. A configured stop percentage may not guarantee an exchange-side stop. | Document and test each limit's semantics: block entries, cancel orders, reduce-only flatten, or emergency shutdown. Verify daily rollover, restarts and timezone behavior. |
| A-10 / **P1** | **Costs are venue/profile-dependent and can be overridden.** `traderbot/utils/trading_costs.py`; `docs/live-trading.md` documents 0.045% taker fee + 0.05% slippage per fill for the default Hyperliquid assumptions, versus different Nobitex assumptions. | Wrong venue inference, stale fee tier, maker/taker misclassification or omitted funding can reverse net edge. | Require explicit venue and market kind for all production evaluations; store cost assumptions with each result and run adverse-cost scenarios. |
| A-11 / **P1** | **Paper/live parity must be demonstrated for all order modes.** `Algorithm.order_size()` docs state live ignores partial sizes; docs also describe separate market and order-engine paths. | A strategy can behave differently despite sharing `on_bar()`. | Add contract tests across strategy × venue × execution mode. Refuse unsupported combinations at startup rather than silently falling back. |
| A-12 / **P2** | **Risk state persistence and restart behavior require proof.** `traderbot/risk/manager.py` keeps day-start, peak and last equity state in memory and provides state serialization methods. | Restarting may reset peak/daily-loss context unless caller persists and restores state correctly. | Test real session persistence, UTC/day rollover and restore validation; persist risk state atomically with versioning. |
| A-13 / **P2** | **Public order-book filter failures are tolerated.** `traderbot/terminal/hyperliquid_trader.py` catches exceptions for public book reads and continues without the filter. | If spread is a required safety condition, missing book data can silently bypass it. | Distinguish optional alpha input from mandatory risk gate. Mandatory filters must fail closed on stale/unavailable data; test websocket/REST outage. |

The table identifies implementation risks and validation requirements; it does not assert that every failure has already occurred in production.

## 5. Profitability and risk framework

### Core calculations

For net trade outcomes:

\[
E = p_w\,\overline{W}_{net} - (1-p_w)\,\overline{L}_{net}
\]

where average wins/losses already include commissions, spread, slippage, funding/borrow costs when applicable, and any other execution costs. Do not subtract costs twice.

Other required measures:

- **Profit factor:** gross net-of-cost winning PnL divided by absolute net-of-cost losing PnL.
- **Maximum drawdown:** largest peak-to-subsequent-trough decline in equity, including unrealized PnL.
- **Turnover:** traded notional relative to equity; useful for identifying cost-heavy strategies.
- **Exposure:** gross/net notional, margin usage, time in market and correlated exposure.
- **Trade count and uncertainty:** a high return from a small number of trades is weak evidence. Report confidence intervals and per-fold results.
- **Tail risk:** worst trade/day, expected shortfall where data supports it, consecutive losses, gap losses and liquidation stress.
- **Capacity:** compare strategy notional with market volume, spread and depth; backtest returns may not scale with size.

For a long market round trip under the documented default Hyperliquid assumptions, the approximate cost is:

\[
2\times(0.045\%+0.05\%)=0.19\%
\]

This is a rough baseline, not a universal rate; actual fee tier, maker/taker mix, market impact and funding vary. At small targets, even modest additional spread or adverse selection can eliminate the gross edge.

### Position sizing

Use risk-based sizing where the venue and strategy support it:

\[
\text{quantity} \approx \frac{\text{equity}\times\text{risk fraction}}{|\text{entry}-\text{stop}|}
\]

Then cap by available capital/margin, leverage, symbol limits, liquidity and portfolio exposure. This is a sizing framework, not a guarantee that realized loss will equal the chosen risk amount: gaps, slippage, partial fills and stop failure can exceed it.

Do not assume an ATR stop automatically improves profitability. Test whether volatility-scaled stops improve out-of-sample expectancy and drawdown after turnover and execution costs.

## 6. Backtesting and validation audit

### Existing strengths visible in source

- `traderbot/backtesting/engine.py` distinguishes close and next-open execution.
- `traderbot/backtesting/broker.py` documents event ordering so prior pending market orders fill at the next open, bracket exits are processed, prior resting limits are evaluated, and only then the algorithm sees the closed bar.
- Tests cover next-open timing and a no-future-bar behavior (`tests/test_backtest_execution.py`).
- The repository has walk-forward validation (`backtesting/walk_forward.py`), research robustness tests (`tests/test_research_robustness.py`), indicator parity tests and temporal-guard tests.
- `tests/test_research_robustness.py` expects a default minimum of 30 trades for sweep/validation eligibility. Thirty trades is a filter, not proof of statistical significance.

### Gaps and risks to validate

1. **Same-close execution:** do not use `close` mode for selecting close-based signals without explicitly acknowledging optimism.
2. **Intrabar order:** when stop and TP are both touched within an OHLC candle, the engine uses stop-first assumptions. This is conservative but does not reconstruct actual path; test lower-timeframe replay sensitivity.
3. **Limit fill model:** price-through fills omit queue position, depth and partial fills; maker fills are not free alpha.
4. **Funding and borrow:** verify that every perpetual strategy's backtest includes actual funding timestamps/rates and the appropriate side; include borrow costs if relevant.
5. **Gaps and data integrity:** enforce monotonic timestamps, unique bars, expected interval, OHLC consistency, nonnegative volume where applicable, and explicit gap reports. Never silently forward-fill price gaps into tradable bars.
6. **Warm-up:** indicator state must use only preceding data; warm-up bars must not contribute to test metrics or leak positions/PnL from training.
7. **Optimization provenance:** store data range, dataset hash, strategy version, code commit, parameter grid, cost model, seed and fold boundaries with every result.
8. **Multiple testing:** thousands of parameter combinations can produce a lucky winner. Prefer a stable plateau and robust OOS folds over a single peak score.
9. **Benchmarks:** compare with buy-and-hold and a simple no-trade/cash baseline on the same period; include turnover and exposure.
10. **Metrics:** use daily/regularly sampled equity returns for Sharpe/Sortino rather than treating overlapping trade outcomes as independent observations without justification.

### Recommended validation protocol

1. Freeze the strategy hypothesis and parameter search space before the final test.
2. Split data chronologically into train, validation and a final untouched holdout; keep the holdout inaccessible to tuning.
3. Run rolling walk-forward folds with a warm-up window and strictly causal features.
4. Use venue-specific maker/taker fees, spread, slippage, funding, precision and minimum-notional assumptions.
5. Stress costs (for example base, 1.5× and 2× costs) as provisional sensitivity scenarios, not forecasts.
6. Report every fold, not only the aggregate: net return, drawdown, trade count, profit factor, average trade, turnover and exposure.
7. Bootstrap trade sequences or daily returns where assumptions are defensible; use block bootstrap for serially dependent returns. Include Monte Carlo order/sequence perturbation if execution uncertainty is important.
8. Paper trade the frozen configuration and compare expected vs actual fills, fees, slippage, funding, rejected orders and signal timing.
9. Promote only after operational checks pass and OOS evidence remains acceptable; then use tiny risk-limited live exposure with explicit rollback criteria.

## 7. Feature recommendations and trade-offs

| Feature | Benefit hypothesis | Complexity | Main downside / dependency | Validation |
|---|---|---|---|---|
| Account-level risk manager | Prevents aggregate overexposure across symbols/strategies | Medium | Requires common equity, margin and exposure view | Multi-symbol loss and correlated crash simulations |
| Fail-closed protective-order verification | Reduces unprotected-position risk | Medium | Can trigger emergency exits during exchange/API outage | Inject stop placement, cancel and reconnect failures |
| Shared sizing contract | Removes backtest/live sizing divergence | Medium | Venue precision and margin semantics differ | Contract tests and order-size parity |
| Spread/liquidity gate | Avoids low-quality fills where costs dominate | Low–medium | Can reduce trade count; book data may be stale | Compare net expectancy by spread bucket |
| ATR/volatility sizing | Normalizes risk across regimes | Medium | ATR stops can widen during stress; gaps exceed stop | Fixed-risk vs fixed-size ablation across regimes |
| Regime classification | May keep mean reversion out of trends and trend systems out of ranges | Medium | Adds model/threshold overfit risk | Predefined simple regime labels and ablation |
| Correlation-aware exposure | Limits duplicate bets on correlated assets | Medium | Correlations change during stress | Historical and stress-period portfolio replay |
| Funding/OI data | Improves perp carry/crowding context | Medium–high | Data quality and timing alignment | Funding-aware PnL and timestamp-leakage tests |
| Book-aware market making | Improves fill/adverse-selection estimates | High | Requires reliable L2 data and replay infrastructure | Live markout, fill ratio, queue and cancel metrics |
| Performance-based suspension | Stops strategies after statistically credible degradation | Medium | Noisy triggers can disable a good strategy | Simulated degradation and false-alarm analysis |
| Trade journal and dashboards | Makes execution and strategy attribution measurable | Low–medium | Storage/observability cost | Completeness checks and reconciliation |
| ML / RL / sentiment | Potentially captures nonlinear effects | High | Large data needs, leakage and overfit risk | Do not prioritize until simpler baselines are robust |

**Recommended order:** safety invariants and sizing parity first; then data/cost integrity and trade attribution; then simple liquidity/risk features; regime/portfolio overlays only after ablation tests. Do not start with ML or reinforcement learning.

## 8. Proposed architecture

Keep the current modular structure, but make these boundaries explicit:

- **MarketDataService:** normalized closed bars, timestamps, gap/staleness checks and venue metadata.
- **Strategy interface:** pure signal/intent generation; no exchange client access and no bypass around risk.
- **PortfolioRiskService:** account-level and per-strategy limits; computes permitted target exposure.
- **SizingService:** converts permitted target exposure into venue-compliant quantity, respecting available margin and minimums.
- **Execution adapter:** venue-specific order submission, idempotency keys, retries, cancel/replace, partial fills and reconciliation.
- **Position/order ledger:** append-only order events and fills; durable recovery after restart.
- **PnL/cost accounting:** realized/unrealized PnL, fees, funding, slippage and equity without double counting.
- **Research runner:** deterministic data snapshot, strategy version, config, folds and output artifacts.
- **Monitoring/alerts:** data stale, risk halt, stop absent, rejected order, mismatch, abnormal latency and drawdown.

A strategy should return a desired action or target exposure, not directly submit orders. The risk layer should have the final say. Execution retries must be idempotent: a timeout after submission is ambiguous, so query by client order ID/status before resubmitting.

Example configuration shape (illustrative; map to existing CLI/config schema before implementing):

```yaml
risk:
  max_daily_loss_pct: 2.0
  max_drawdown_pct: 8.0
  max_gross_exposure_equity: 1.0
  max_positions: 2
  require_protective_stop: true
  fail_closed_on_stale_data: true
execution:
  mode: paper
  idempotent_client_order_ids: true
  reconcile_before_entry: true
research:
  signal_fill_model: next_open
  record_dataset_hash: true
  require_untouched_holdout: true
```

These are example fields, not claims that current config accepts them or recommended final risk limits. Calibrate risk values to capital, leverage, liquidity and drawdown tolerance.

## 9. Prioritized implementation plan

| Priority | Work | Evidence / location | Expected benefit hypothesis | Complexity | Acceptance test |
|---|---|---|---|---|---|
| **P0** | Enforce strategy × venue capability matrix; reject unsupported partial sizing/order modes | `algorithms/base.py`, live traders | Prevents live exposure diverging from research | Medium | Tests show sizing and state semantics match for all supported paths |
| **P0** | Verify protective orders after fills; explicit fallback on missing stop | `hyperliquid/order_manager.py`, `docs/live-trading.md` | Reduces catastrophic unprotected-position risk | Medium–high | Stop failures, partial fills and reconnects never silently leave required protection absent |
| **P0** | Add portfolio/account-level limits | `risk/manager.py`, live terminal | Prevents cumulative multi-symbol risk exceeding budget | Medium | Simulated correlated drawdown blocks further risk consistently |
| **P0** | Make exchange reconciliation and restart recovery deterministic | `terminal/hyperliquid_trader.py`, `traders/inventory_reconcile.py` | Reduces orphan orders and position mismatch | High | Crash/restart tests recover actual position/order state before new entries |
| **P1** | Use causal execution and realistic cost profiles for selection | `backtesting/engine.py`, `utils/trading_costs.py` | Avoids selecting edges erased by execution costs | Low–medium | All reports record fill model, fee, slippage and funding assumptions |
| **P1** | Fail closed for missing optimization provenance in holdout selection | `algorithms/optimized_params.py` | Reduces temporal leakage risk | Low–medium | Missing/malformed timestamps cannot feed holdout/live parameter selection |
| **P1** | Add live-vs-backtest execution attribution | `terminal/events.py`, order manager, results | Shows whether edge is lost to spread, slippage or fill rate | Medium | Every fill can be linked to signal, expected price and realized cost |
| **P1** | Add data-quality gates and stale-book policy | `data/bar_cache.py`, `terminal/hyperliquid_trader.py` | Prevents decisions on invalid/stale inputs | Medium | Gap, duplicate, stale and book outage tests behave explicitly |
| **P2** | Portfolio correlation and liquidity-aware risk budgets | risk/data layer | Reduces concentrated exposure and poor fills | Medium | Improves stress metrics without unacceptable OOS edge loss |
| **P2** | Strategy-level monitoring and degradation alerts | lab/results/live events | Detects drift and execution deterioration sooner | Medium | Alerts are tested against synthetic failure events |
| **P3** | Regime filter, funding/OI, order-book alpha, ML | individual research branches | Possible incremental edge, unproven | Medium–high | Promote only after pre-registered OOS ablation succeeds |

### Phases and gates

**Phase 0 — Safety before any live experiment**
- Keep paper mode as default.
- Test position sizing parity, risk semantics, stop verification, idempotency, and reconciliation.
- Gate: no known critical order-state or sizing mismatch; all safety fault-injection tests pass.

**Phase 1 — Trustworthy research**
- Enforce closed-bar data, gap/duplicate validation, causal fills, venue costs and reproducible artifacts.
- Gate: backtest reports reproduce from a pinned commit and dataset; temporal split tests pass.

**Phase 2 — Strategy baselines**
- Compare simple trend, mean-reversion and breakout baselines using identical data and costs.
- Gate: adequate trade count, positive net expectancy across multiple OOS folds, and no unacceptable single-regime dependence. Thresholds should be calibrated to the intended deployment and uncertainty, not chosen after seeing the holdout.

**Phase 3 — Paper execution**
- Run frozen parameters; compare signal, fill, fee, slippage, funding and inventory reconciliation against expectations.
- Gate: stable operations and explainable differences between simulated and paper results.

**Phase 4 — Limited live pilot**
- Only after prior gates, use minimum feasible size and strict account-level caps. Monitor manually; automatic stop/rollback is required.
- Gate: no unresolved safety incident, consistent reconciliation, and observed costs within the predeclared stress envelope.

**Phase 5 — Incremental research**
- Test one enhancement at a time; preserve baseline and ablation results. Never promote solely because one historical run has the highest return.

## 10. Experiment plan

Use the same dataset snapshot, folds, initial capital, cost model and benchmark for baseline and variant. Change one factor at a time.

| Experiment | Hypothesis / single change | Data and comparison | Metrics / rejection criteria |
|---|---|---|---|
| E1: Fill-model sensitivity | Next-open/order-aware fills reduce optimistic bias versus close fills | Same strategies and bars; compare `close` vs `next_open` and conservative cost assumptions | Reject any conclusion that exists only under close fills or disappears under modest cost stress |
| E2: Cost sensitivity | Some apparent edges are too small to survive realistic costs | Per-venue fees, spread/slippage buckets and funding where applicable | Reject if net expectancy becomes negative under plausible cost variation |
| E3: Scalp viability | Scalp-dip can or cannot overcome turnover costs | BTC/ETH at 1m and 5m, multiple market regimes, fixed folds; compare legacy vs maker/bracket modes | Report net expectancy, turnover, fill ratio, drawdown and trade count; reject if OOS net edge is unstable or fill assumptions drive results |
| E4: Breakout baseline | ATR breakout has a robust trend edge | BTC/ETH and other sufficiently liquid supported pairs; hourly and 15m as separate hypotheses | Fold-by-fold return, drawdown, average trade, exposure and sensitivity; reject isolated parameter peaks |
| E5: Simple regime gate | A predeclared trend/range gate improves a single baseline | Same folds; one regime filter only, no retuning on holdout | Accept only if incremental OOS net expectancy and drawdown trade-off repeat across folds |
| E6: Sizing policy | Volatility/risk-based sizing improves portfolio risk without eliminating edge | Same entry/exit signals; compare fixed fraction vs risk-per-stop | Compare max DD, expected shortfall, turnover, return and exposure; reject if risk appears lower only due to lower invested capital without normalized comparison |
| E7: Portfolio limits | Aggregate caps reduce correlated drawdown | Multi-asset portfolio, same signal streams | Evaluate worst drawdown, margin, exposure and return; ensure caps are applied to total account rather than independently |
| E8: Live fill calibration | Simulated maker/taker fills approximate actual execution sufficiently | Paper/testnet or controlled minimal-size logs with signal and order timestamps | Compare fill rate, latency, realized spread, slippage, fees and cancellation; recalibrate or disable strategy if model is systematically optimistic |

### Provisional acceptance discipline

- Predefine the primary metric and rejection rules before each run.
- Report confidence intervals and every walk-forward fold, not only aggregate performance.
- Require positive net expectancy with adequate sample size and acceptable drawdown; do not use a single arbitrary ROI target.
- Compare strategies on equal risk or clearly normalize for exposure and leverage.
- Preserve a final holdout for one-time evaluation. If it is used to choose parameters, it is no longer an untouched holdout.
- Keep a paper/live shadow baseline while changing only one component.

## 11. Test, monitoring and deployment checklists

### Research and data
- [ ] Bars are closed, ordered, unique and aligned to the expected interval.
- [ ] Gaps, stale candles, invalid OHLC values and exchange outages are surfaced.
- [ ] Indicators warm up without reading future bars.
- [ ] Dataset, code commit, parameters, costs, seed and date ranges are saved.
- [ ] Backtests include fees, slippage, funding/borrow where applicable and realistic fills.
- [ ] Walk-forward and untouched holdout are not used for tuning.
- [ ] Metrics include net expectancy, profit factor, drawdown, turnover, exposure and trade count.

### Execution and risk
- [ ] Strategy/venue capability is validated before session start.
- [ ] Exchange state and open orders are reconciled before any new entry.
- [ ] Order submission is idempotent across ambiguous timeouts.
- [ ] Partial fills, rejected orders, cancel/replace and stop/TP sibling cancellation are tested.
- [ ] Protective stop presence is verified when required.
- [ ] Account-wide risk, margin and exposure limits apply across symbols.
- [ ] Kill switch semantics are explicit; exits and reduce-only actions remain possible.
- [ ] Credentials are not logged; API permissions are least-privilege; live keys are separated from research environments.
- [ ] Restart recovery, stale data, rate limits, websocket fallback and clock skew are tested.

### Operations
- [ ] Alert on missing protection, exchange/inventory mismatch, repeated rejection, stale data and abnormal slippage.
- [ ] Every fill is journaled with order ID, strategy, signal timestamp, requested/filled size, price, fee and venue.
- [ ] Equity and PnL accounting avoids double counting unrealized PnL.
- [ ] Rollback path is tested and live risk can be disabled without disabling exits.
- [ ] Deployments are pinned to a reviewed commit and config; no unattended parameter auto-promotion.

## 12. Five improvements to implement first

1. **Sizing and execution parity** across backtest, paper and live; reject unsupported modes instead of silently approximating them.
2. **Protective-order verification and emergency handling** for every order path that claims to use a stop.
3. **Account-level risk limits** spanning all symbols, strategies and open orders.
4. **Durable reconciliation and idempotent order recovery** across partial fills, network ambiguity and process restarts.
5. **Cost-aware, temporally clean validation** with reproducible datasets, next-open or realistic fills, explicit venue costs and untouched holdout.

## 13. Retain, improve, test further or disable

- **Retain as baselines:** SMA/EMA cross, MA trend, RSI, MACD, Bollinger and ATR breakout. Their value must be established independently by market/timeframe.
- **Improve and validate:** common sizing semantics, risk manager integration, exchange reconciliation, order lifecycle persistence, cost attribution and temporal provenance.
- **Test further in paper/research:** ensemble, pair trading, funding carry, grid/DCA, market making, momentum shock, chart patterns, online logistic and FinRL variants.
- **Do not promote to live based on repository presence alone:** `scalp_dip` (its own comment says the referenced 5m preset was not profitable OOS), and Hyperliquid order-engine paths until live exchange lifecycle behavior is exercised and reconciled.
- **Disable any live combination** that depends on partial sizing or required protective orders when that capability is not confirmed in the selected execution path.

“Disable” here means keep out of live deployment until the gate passes; it does not mean delete the strategy from research.

## 14. Questions not answerable from static code alone

1. Which strategy has positive net expectancy on current, representative data?
2. What are the actual live fill rates, spread costs, slippage, funding and rejection rates?
3. Are the current fee assumptions accurate for the account's fee tier and order types?
4. How do returns and drawdowns change across market regimes and unseen assets?
5. Does the exchange's current API behavior match the assumed order-status and stop-trigger lifecycle?
6. Are production credentials restricted to the minimum required permissions and protected outside the repository?
7. What is the maximum acceptable daily loss, account drawdown, leverage and total exposure for the intended capital?
8. Are stored backtest results generated from the current code and dataset version, or from older versions?
9. Does the full test suite pass in a clean Python 3.12 environment, including optional dependency paths?
10. What is the live-vs-backtest performance gap after matching timestamps, sizing, fills, fees and funding?

## 15. Final recommendation

Treat this project first as a **research and execution-integrity system**, then as a strategy competition. Freeze strategy expansion until the execution contract, portfolio risk, protective-order invariants, reconciliation and cost accounting are demonstrated by tests. Establish a credible baseline with chronological walk-forward results and realistic costs. Only then test regime filters, dynamic sizing or more complex strategies, one hypothesis at a time.

The goal is not the best historical equity curve. It is a strategy whose net edge survives costs, out-of-sample periods, market regime changes and imperfect execution without violating predefined risk limits.
