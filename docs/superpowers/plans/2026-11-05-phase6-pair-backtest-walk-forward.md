# Implementation Plan - Phase 6: Upgrade Existing Pair Backtesting & Walk-Forward Validation

**Document Status:** Ready for Execution  
**Target Architecture:** `traderbot/backtesting/` (`pair_engine.py`, `pairs.py`, `walk_forward.py`, `validation.py`, `metrics.py`, `fills.py`, `broker.py`)  
**Protocol Alignment:**  
- `.agents/skills/lookahead-bias-elimination/SKILL.md`  
- `.agents/skills/execution-realistic-simulation/SKILL.md`  
- `.agents/skills/walk-forward-validation-setup/SKILL.md`  
- `.agents/skills/perpetual-futures-funding-rate-handling/SKILL.md`

---

## 1. Executive Summary & Architecture Map

### Purpose
Transform existing single-asset and pair backtesting modules into an institutional-grade, multi-pair statistical arbitrage backtesting and chronological walk-forward validation system with:
1. Strictly causal timing (`execution="next_open"` default, zero lookahead).
2. Friction-aware execution (maker/taker fee modeling, bid-ask spread crossing, square-root market impact, legging risk).
3. Sound margin & perpetual accounting (realized/unrealized PnL, discrete funding settlement, terminal liquidation marking).
4. Rigorous walk-forward validation with expanding/rolling windows and `max(L, H)` purge/embargo gaps to prevent target and feature leakage.

### Affected Modules & File Boundaries
| File | Responsibility | Planned Changes |
|---|---|---|
| [`traderbot/backtesting/pair_engine.py`](file:///Users/m/Code/trade/traderbot/traderbot/backtesting/pair_engine.py) | High-performance pair backtest engine | Add `execution="next_open"`, terminal liquidation marking, funding tracking, portfolio multi-pair engine, legging failure modeling |
| [`traderbot/backtesting/pairs.py`](file:///Users/m/Code/trade/traderbot/traderbot/backtesting/pairs.py) | Original spot/market-neutral pair backtester | Fix short accounting inversion bug, align API with `pair_engine.py`, add benchmark baseline generation |
| [`traderbot/backtesting/walk_forward.py`](file:///Users/m/Code/trade/traderbot/traderbot/backtesting/walk_forward.py) | Walk-forward optimization engine | Extend to support pair backtests, expanding vs. rolling modes, purge/embargo gap `max(L, H)`, parameter stability & dispersion metrics |
| [`traderbot/backtesting/validation.py`](file:///Users/m/Code/trade/traderbot/traderbot/backtesting/validation.py) | Validation & causality auditing | Update `audit_backtest_causality()` to audit `PairBacktestResult` and verify bar-by-bar execution monotonicity |
| [`traderbot/backtesting/metrics.py`](file:///Users/m/Code/trade/traderbot/traderbot/backtesting/metrics.py) | Quantitative performance calculations | Implement annualized Sharpe, Sortino, Calmar, Profit Factor, Expectancy, Turnover, Gross/Net exposure time series |
| [`traderbot/backtesting/fills.py`](file:///Users/m/Code/trade/traderbot/traderbot/backtesting/fills.py) | Realistic fill models | Add square-root market impact model $I(Q) = \gamma \sigma \sqrt{Q/V}$, spread crossing logic, maker post-only acceptance |
| [`traderbot/backtesting/broker.py`](file:///Users/m/Code/trade/traderbot/traderbot/backtesting/broker.py) | Single-asset broker simulation | Expose shared fill and cost utilities for multi-asset engine compatibility |

---

## 2. Phased Implementation Plan

### Phase 1: Accounting Audit & Terminal Mark-to-Market Fixes
**Goal:** Prove mathematical precision in cash, margin, realized PnL, unrealized PnL, funding payments, and terminal liquidation.

#### Tasks:
1. **Fix `pairs.py` legacy short accounting:**
   - In `run_pairs_backtest`, replace buggy short subtraction with correct margin-collateral accounting where short sale proceeds are tracked and buying to cover deducts cash.
2. **Terminal Liquidation in `pair_engine.py`:**
   - At the final bar of the backtest, if positions are still open, calculate both:
     - `marked_equity`: raw mid-price marked equity without closing friction.
     - `liquidated_equity`: cash after closing both legs with slippage and taker fees.
   - Store both in `PairBacktestResult` and ensure `final_equity` reflects terminal liquidation or explicitly flags open risk.
3. **Discrete Funding Rate Accounting:**
   - Ensure funding deductions reflect venue settlement intervals (e.g. 1h on Hyperliquid).
   - Track `total_funding_paid` and `total_funding_received` as explicit fields on `PairBacktestResult`.

#### Tests:
- `tests/test_pair_trading_accounting.py`:
  - `test_pair_engine_terminal_liquidation_deducts_closing_costs()`
  - `test_pair_engine_funding_payment_tracking()`
  - `test_pairs_legacy_short_accounting_math()`

---

### Phase 2: Causality Enforcement & Next-Open Execution
**Goal:** Eliminate same-bar fill contamination in pair trading per `.agents/skills/lookahead-bias-elimination/SKILL.md`.

#### Tasks:
1. **Decouple Signal from Execution:**
   - Modify `run_perp_pair_backtest` and `run_pair_backtest` to accept `execution: Literal["next_open", "close"] = "next_open"`.
   - In `next_open` mode:
     - Signal computed at bar $T$ close.
     - Orders filled at bar $T+1$ open prices (`bar["open"]` and `bar["hedge_open"]`).
   - Store `execution` attribute on `PairBacktestResult`.
2. **Causality Auditor Integration:**
   - Enhance `audit_backtest_causality()` in `validation.py` to recognize `PairBacktestResult` and `PairTrade`.
   - Verify timestamp strictly increases and no same-bar fills occur under `next_open`.

#### Tests:
- `tests/test_backtest_causality_audit.py`:
  - `test_pair_backtest_causality_clean_next_open()`
  - `test_pair_backtest_flags_same_bar_close()`

---

### Phase 3: Realistic Execution Model & Legging Risk
**Goal:** Simulate realistic market microstructure frictions per `.agents/skills/execution-realistic-simulation/SKILL.md`.

#### Tasks:
1. **Spread & Market Impact Model in `fills.py`:**
   - Implement `calculate_slippage_and_impact(price, qty, volume, volatility, spread_pct, gamma)`:
     - Spread cost: half-spread crossing for taker orders.
     - Impact cost: $\Delta P = \gamma \cdot \sigma \cdot \sqrt{\frac{Q}{V}} \cdot P_{\text{mid}}$.
2. **Legging Execution Simulation in `pair_engine.py`:**
   - Parameter `legging_latency_bars`: simulate delay between Leg A fill and Leg B fill.
   - Legging failure policy: when Leg B fails or aborts, calculate adverse move cost of unwinding Leg A.

#### Tests:
- `tests/test_pair_realistic_execution.py`:
  - `test_square_root_market_impact_scaling()`
  - `test_bid_ask_spread_crossing_costs()`
  - `test_legging_delay_and_abort_unwind()`

---

### Phase 4: Strategy Modes, Dynamic Hedge Ratios & Multi-Pair Portfolio
**Goal:** Enable comprehensive pair trading features across spot and perpetual markets.

#### Tasks:
1. **Support Dynamic Rolling Hedge Ratio:**
   - Support Kalman filter or rolling OLS hedge ratio $\beta_t$ updated strictly point-in-time.
2. **Cointegration Breakdown Protection:**
   - Halt new entries and trigger emergency flattening when ADF test p-value exceeds `p_value_threshold` (e.g. 0.10) or half-life exceeds `max_half_life`.
3. **Multi-Pair Portfolio Backtest Engine:**
   - Add `run_multi_pair_backtest(pairs_data, algorithm_factory, capital)` in `pair_engine.py` to simulate concurrent trading of multiple cointegrated pairs with shared margin pool and gross exposure limits.

#### Tests:
- `tests/test_pair_portfolio_engine.py`:
  - `test_multi_pair_concurrent_position_limits()`
  - `test_cointegration_breakdown_trigger_halts_trading()`

---

### Phase 5: Institutional Performance Metrics & Benchmark Suite
**Goal:** Provide full quantitative analytics suite in `metrics.py` and tear-sheet generators.

#### Tasks:
1. **Comprehensive Metric Functions:**
   - `annualized_sharpe(returns, periods_per_year=8760)`
   - `annualized_sortino(returns, periods_per_year=8760)`
   - `calmar_ratio(cagr_pct, max_dd_pct)`
   - `profit_factor(trades)`
   - `expectancy(trades)`
   - `turnover_and_exposure_metrics(equity_curve, exposure_curve)`
2. **Benchmark Generators:**
   - Generate Buy & Hold A, Buy & Hold B, 50/50 Equal-Weight, and Cash baselines for exact apples-to-apples comparison.

#### Tests:
- `tests/test_backtest_metrics.py`:
  - `test_sharpe_sortino_zero_drawdown_handling()`
  - `test_profit_factor_and_expectancy_accuracy()`
  - `test_benchmark_comparison_generators()`

---

### Phase 6: Chronological Walk-Forward Engine with Purge/Embargo
**Goal:** Implement institutional walk-forward optimization per `.agents/skills/walk-forward-validation-setup/SKILL.md`.

#### Tasks:
1. **Expanding & Rolling Window Partitioning:**
   - Support `mode: Literal["rolling", "expanding"] = "rolling"`.
   - Calculate purge/embargo gap: $\text{gap} = \max(\text{lookback\_bars}, \text{holding\_bars})$.
2. **Pair Walk-Forward Engine:**
   - Create `run_pair_walk_forward(options: PairWalkForwardOptions)` in `walk_forward.py`.
   - Optimize parameters on train split; validate on embargoed OOS fold; compound strictly OOS returns.
3. **No Peeking Invariant:**
   - Ensure final holdout dataset is never peeked during parameter selection.

#### Tests:
- `tests/test_walk_forward_pairs.py`:
  - `test_walk_forward_purge_embargo_gap_enforcement()`
  - `test_expanding_vs_rolling_windows_splits()`
  - `test_pair_walk_forward_oos_compounding()`

---

### Phase 7: Parameter Stability, PBO & Lab Catalog Integration
**Goal:** Evaluate parameter sensitivity, report performance dispersion, and persist artifacts.

#### Tasks:
1. **Parameter Sensitivity & Stability Metrics:**
   - Calculate parameter dispersion across folds (coefficient of variation of optimal parameters).
   - Compute in-sample vs out-of-sample Sharpe degradation ratio ($SR_{\text{OOS}} / SR_{\text{IS}}$).
2. **Artifact Generation & Lab Store:**
   - Generate equity curve JSON, drawdown series, spread/z-score series, trade history CSV, and tearsheet report.
   - Store in `results/` following Traderbot Lab catalog schema.

#### Tests:
- `tests/test_parameter_stability.py`:
  - `test_parameter_dispersion_calculation()`
  - `test_walk_forward_tearsheet_export()`

---

## 3. Verification & Compliance Checklist
- [ ] Causality: `audit_backtest_causality()` passes 100% with `is_causal=True` on `next_open`.
- [ ] Accounting: Realized PnL + Unrealized PnL + Fees + Funding = Total Change in Equity.
- [ ] No Lookahead: Zero same-bar fills; OLS beta computed on past bars only.
- [ ] Walk-Forward: Zero overlapping train/test samples; purge gap strictly $\ge \max(L, H)$.
- [ ] Test Suite: Full pytest suite passes cleanly (`.venv/bin/pytest tests/test_*pair*.py tests/test_*walk_forward*.py`).

