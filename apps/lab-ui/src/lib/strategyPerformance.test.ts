import { describe, expect, it } from "vitest";

import {
  compareByAvgThenBestReturn,
  filterPerformanceRows,
  formatStrategyPerformanceLabel,
  isCompleteCatalogStats,
  isCompleteLivePreview,
  isModelDrivenStrategy,
  pickBestMatchByAvgAndMax,
  sortPerformanceRows,
  type PerformanceRow,
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

  const sampleRows: PerformanceRow[] = [
    {
      id: "sma_cross",
      name: "SMA Trend Cross",
      style: "trend",
      summary: "Moving average crossover",
      catalogRuns: 10,
      catalogAvg: 3.5,
      catalogBest: 8.0,
      catalogWinRate: 65.0,
      previewReturn: 2.1,
      previewDrawdown: 4.0,
      previewTrades: 12,
      previewWinRate: 58.0,
      sweepReturn: 5.0,
      sweepHoldout: 3.0,
      rank: 1,
    },
    {
      id: "rsi_threshold",
      name: "RSI Mean Reversion",
      style: "mean_reversion",
      summary: "Oversold buy / overbought sell",
      catalogRuns: 5,
      catalogAvg: -1.2,
      catalogBest: 2.0,
      catalogWinRate: 42.0,
      previewReturn: -0.5,
      previewDrawdown: 6.5,
      previewTrades: 8,
      previewWinRate: 40.0,
      sweepReturn: 1.0,
      sweepHoldout: -0.5,
      rank: 2,
    },
    {
      id: "online_logistic",
      name: "Online Logistic ML",
      style: "ml",
      summary: "Adaptive classifier",
      catalogRuns: 0,
      catalogAvg: null,
      catalogBest: null,
      catalogWinRate: null,
      previewReturn: null,
      previewDrawdown: null,
      previewTrades: null,
      previewWinRate: null,
      sweepReturn: null,
      sweepHoldout: null,
      rank: null,
    },
  ];

  it("filters strategies by query search", () => {
    const res = filterPerformanceRows(sampleRows, { query: "RSI" });
    expect(res).toHaveLength(1);
    expect(res[0].id).toBe("rsi_threshold");
  });

  it("filters strategies by style", () => {
    const res = filterPerformanceRows(sampleRows, { style: "trend" });
    expect(res).toHaveLength(1);
    expect(res[0].id).toBe("sma_cross");
  });

  it("filters strategies by outcome", () => {
    const profitable = filterPerformanceRows(sampleRows, { outcome: "profitable" });
    expect(profitable).toHaveLength(1);
    expect(profitable[0].id).toBe("sma_cross");

    const loss = filterPerformanceRows(sampleRows, { outcome: "loss" });
    expect(loss).toHaveLength(1);
    expect(loss[0].id).toBe("rsi_threshold");
  });

  it("filters strategies by win rate", () => {
    const high = filterPerformanceRows(sampleRows, { winRate: "high" });
    expect(high).toHaveLength(1);
    expect(high[0].id).toBe("sma_cross");

    const low = filterPerformanceRows(sampleRows, { winRate: "low" });
    expect(low).toHaveLength(1);
    expect(low[0].id).toBe("rsi_threshold");

    const numeric55 = filterPerformanceRows(sampleRows, { winRate: "55" });
    expect(numeric55).toHaveLength(1);
    expect(numeric55[0].id).toBe("sma_cross");

    const numeric70 = filterPerformanceRows(sampleRows, { winRate: "70" });
    expect(numeric70).toHaveLength(0);
  });

  it("filters strategies by detailed outcome", () => {
    const posCat = filterPerformanceRows(sampleRows, { outcome: "positive_catalog" });
    expect(posCat).toHaveLength(1);
    expect(posCat[0].id).toBe("sma_cross");

    const posPreview = filterPerformanceRows(sampleRows, { outcome: "positive_preview" });
    expect(posPreview).toHaveLength(1);
    expect(posPreview[0].id).toBe("sma_cross");
  });

  it("filters strategies by activity (complete only)", () => {
    const complete = filterPerformanceRows(sampleRows, { activity: "complete_only" });
    expect(complete).toHaveLength(2);
    expect(complete.map((r) => r.id)).toEqual(["sma_cross", "rsi_threshold"]);
  });

  it("sorts strategies by win rate and name", () => {
    const sortedWr = sortPerformanceRows(sampleRows, "catalog_win_rate_desc");
    expect(sortedWr[0].id).toBe("sma_cross");

    const sortedCombinedWr = sortPerformanceRows(sampleRows, "win_rate_desc");
    expect(sortedCombinedWr[0].id).toBe("sma_cross");

    const sortedAvgAsc = sortPerformanceRows(sampleRows, "catalog_avg_asc");
    expect(sortedAvgAsc[0].id).toBe("rsi_threshold");

    const sortedName = sortPerformanceRows(sampleRows, "name_asc");
    expect(sortedName[0].id).toBe("online_logistic");
  });
});
