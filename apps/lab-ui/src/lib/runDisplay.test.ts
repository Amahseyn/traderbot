import { describe, expect, it } from "vitest";
import type { EvaluationRun } from "@/lib/api";
import { formatResolutionLabel, parseReturnPct } from "@/lib/format";
import {
  extractWinRatePct,
  isRunOptimized,
  runIntervalLabel,
  runListMetrics,
  runParametersList,
  runParametersSummary,
} from "@/lib/runDisplay";

describe("runDisplay parameter and optimizer helpers", () => {
  const baseRun: EvaluationRun = {
    id: "run-12345678",
    run_kind: "strategy_backtest",
    config_id: "cfg-123",
    strategy_id: "sma_cross",
    model_id: null,
    symbol: "BTCIRT",
    resolution: "60",
    horizon_label: null,
    parameters: {
      algorithm: "sma_cross",
      fast: 5,
      slow: 20,
      price_confirm: false,
    },
    optimizer_enabled: true,
    data_context: {},
    metrics: {},
    created_at_utc: "2026-11-03T20:00:00Z",
    compare_session_id: null,
    experiment_id: null,
    dataset_id: null,
    dataset_label: "BTCIRT 1h",
    results_download_url: "/api/runs/run-123/artifact?file=results.json",
  };

  it("extracts all parameters without trimming", () => {
    const list = runParametersList(baseRun);
    expect(list).toEqual([
      { key: "fast", value: 5 },
      { key: "slow", value: 20 },
      { key: "price_confirm", value: false },
    ]);
  });

  it("formats parameters cleanly as a string summary", () => {
    const summary = runParametersSummary(baseRun);
    expect(summary).toBe("fast: 5, slow: 20, !price_confirm");
  });

  it("detects optimizer enabled status accurately", () => {
    expect(isRunOptimized(baseRun)).toBe(true);

    const unoptimizedRun: EvaluationRun = {
      ...baseRun,
      optimizer_enabled: false,
    };
    expect(isRunOptimized(unoptimizedRun)).toBe(false);

    const legacyOptimizedRun: EvaluationRun = {
      ...baseRun,
      optimizer_enabled: undefined,
      data_context: { use_optimized_strategy_params: true },
    };
    expect(isRunOptimized(legacyOptimizedRun)).toBe(true);
  });

  it("extracts win rate percentage from metrics sources", () => {
    // 1. Direct win_rate_pct
    expect(extractWinRatePct({ win_rate_pct: 62.5 })).toBe(62.5);

    // 2. Fractional trade_win_rate (0..1)
    expect(extractWinRatePct({ trade_win_rate: 0.55 })).toBe(55);

    // 3. Percentage trade_win_rate (>1)
    expect(extractWinRatePct({ trade_win_rate: 55.0 })).toBe(55.0);

    // 4. Fractional win_rate
    expect(extractWinRatePct({ win_rate: 0.72 })).toBe(72);

    // 5. vectorbt metrics object
    expect(extractWinRatePct({ vectorbt: { win_rate_pct: 48.0 } })).toBe(48.0);

    // 6. vbt_win_rate_pct
    expect(extractWinRatePct({ vbt_win_rate_pct: 51.5 })).toBe(51.5);

    // 7. Fallback to trade_logs round-trip calculation
    const logs = [
      { action: "buy", price: 100, cash_before: 10000, position_after: 1, equity_after: 10000 },
      { action: "sell", price: 110, position_after: 0, equity_after: 10100 }, // win
      { action: "buy", price: 110, cash_before: 10100, position_after: 1, equity_after: 10100 },
      { action: "sell", price: 90, position_after: 0, equity_after: 9900 },   // loss
    ];
    expect(extractWinRatePct({ trade_logs: logs, initial_cash: 10000 })).toBe(50);

    // 8. Empty or missing metrics
    expect(extractWinRatePct(undefined)).toBeNull();
    expect(extractWinRatePct({})).toBeNull();
  });

  it("includes winRatePct in runListMetrics", () => {
    const runWithWinRate: EvaluationRun = {
      ...baseRun,
      metrics: {
        return_pct: 12.5,
        trades: 10,
        trade_win_rate: 0.6,
      },
    };
    const metrics = runListMetrics(runWithWinRate);
    expect(metrics.returnPct).toBe(12.5);
    expect(metrics.trades).toBe(10);
    expect(metrics.winRatePct).toBe(60);
  });

  it("calculates netPnl correctly using cash_flow fallback", () => {
    const runWithCashFlow: EvaluationRun = {
      ...baseRun,
      metrics: {
        final_equity: 10500,
        cash_flow: {
          initial_cash: 10000,
        },
      },
    };
    const metrics = runListMetrics(runWithCashFlow);
    expect(metrics.netPnl).toBe(500);
  });

  it("formats compound resolutions cleanly", () => {
    expect(formatResolutionLabel("60_last24h")).toBe("1 hour candles (last24h)");
    expect(formatResolutionLabel("60_full_holdout24h")).toBe("1 hour candles (full_holdout24h)");
    expect(formatResolutionLabel("15")).toBe("15 minutes candles");
    expect(formatResolutionLabel("D")).toBe("1 day");
  });

  it("extracts return percentage from cash_flow fallback", () => {
    expect(parseReturnPct({ cash_flow: { return_pct: 8.75 } })).toBe(8.75);
    expect(parseReturnPct({ return_pct: "-4.2" })).toBe(-4.2);
  });

  it("extracts win rate percentage from string inputs", () => {
    expect(extractWinRatePct({ win_rate_pct: "58.4%" })).toBe(58.4);
    expect(extractWinRatePct({ win_rate_pct: "62.0" })).toBe(62.0);
  });
});

