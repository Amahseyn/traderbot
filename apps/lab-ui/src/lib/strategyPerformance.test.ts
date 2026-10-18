import { describe, expect, it } from "vitest";

import {
  compareByAvgThenBestReturn,
  formatStrategyPerformanceLabel,
  isCompleteCatalogStats,
  isCompleteLivePreview,
  isModelDrivenStrategy,
  pickBestMatchByAvgAndMax,
} from "@/lib/strategyPerformance";

describe("isModelDrivenStrategy", () => {
  it("flags ml and meta styles", () => {
    expect(isModelDrivenStrategy({ id: "x", style: "ml" })).toBe(true);
    expect(isModelDrivenStrategy({ id: "x", style: "meta" })).toBe(true);
    expect(isModelDrivenStrategy({ id: "sma_cross", style: "trend" })).toBe(false);
  });

  it("flags finrl and known model ids", () => {
    expect(isModelDrivenStrategy({ id: "finrl_ema_intraday", style: "trend" })).toBe(true);
    expect(isModelDrivenStrategy({ id: "online_logistic", style: "trend" })).toBe(true);
    expect(isModelDrivenStrategy({ id: "ensemble", style: "trend" })).toBe(true);
  });
});

describe("formatStrategyPerformanceLabel", () => {
  it("appends preview return when rank data exists", () => {
    const label = formatStrategyPerformanceLabel("RSI", {
      strategy_id: "rsi_threshold",
      rank: 2,
      return_pct: 1.25,
      trade_count: 4,
    });
    expect(label).toContain("#2");
    expect(label).toContain("+1.25%");
    expect(label).toContain("4 trades");
  });

  it("returns the name when preview is missing", () => {
    expect(formatStrategyPerformanceLabel("SMA", undefined)).toBe("SMA");
  });
});

describe("catalog completeness and best match", () => {
  it("requires runs and a return for complete catalog stats", () => {
    expect(isCompleteCatalogStats(0, 1, 2)).toBe(false);
    expect(isCompleteCatalogStats(3, null, null)).toBe(false);
    expect(isCompleteCatalogStats(2, 0.5, null)).toBe(true);
    expect(isCompleteCatalogStats(1, null, 1.2)).toBe(true);
  });

  it("picks best match by avg then max return", () => {
    const rows = [
      { id: "a", avg_return: 1.0, best_return: 5.0 },
      { id: "b", avg_return: 2.0, best_return: 3.0 },
      { id: "c", avg_return: 2.0, best_return: 4.0 },
      { id: "d", avg_return: 1.0, best_return: null },
    ];
    expect(pickBestMatchByAvgAndMax(rows)?.id).toBe("c");
    expect(compareByAvgThenBestReturn(rows[2], rows[1])).toBeLessThan(0);
  });

  it("flags finite live preview returns as complete", () => {
    expect(isCompleteLivePreview(null)).toBe(false);
    expect(isCompleteLivePreview(Number.NaN)).toBe(false);
    expect(isCompleteLivePreview(0.25)).toBe(true);
  });
});
