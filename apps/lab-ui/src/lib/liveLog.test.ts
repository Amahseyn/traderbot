import { describe, expect, it } from "vitest";
import {
  buyAndHoldEquity,
  countLiveFillStats,
  computeLiveSessionMetrics,
  formatLiveLogPhaseSummary,
  formatLivePositionLabel,
  isLiveSessionInPosition,
  parseLiveEquitySeries,
  parseLiveTickStats,
  summarizeLiveJobLog,
  trimBarsFromSessionStart,
} from "./liveLog";

const SAMPLE_LOG = `
{"event": "paper_wallet", "initial_cash": 1000, "quote_currency": "usdt"}
{"terminal": "live", "strategy": "dca"}
{"event": "tick", "poll": 1, "status": "evaluated", "bar_timestamp": 1700000000, "portfolio": {"quote_cash": 1000, "quote_currency": "usdt", "base_amount": 0, "equity": 1000, "mark_price": 100}}
{"event": "signal", "action": "buy", "timestamp": 1700003600, "close": 102, "mode": "paper", "portfolio": {"quote_cash": 200, "quote_currency": "usdt", "base_amount": 7.84, "equity": 999.68, "mark_price": 102, "base_value": 799.68}}
{"event": "tick", "poll": 2, "status": "no_new_bar", "bar_timestamp": 1700003600, "portfolio": {"quote_cash": 200, "quote_currency": "usdt", "base_amount": 7.84, "equity": 1000.16, "mark_price": 102}}
`.trim();

describe("parseLiveEquitySeries", () => {
  it("collects wallet and portfolio points in order", () => {
    const series = parseLiveEquitySeries(SAMPLE_LOG);
    expect(series.length).toBeGreaterThanOrEqual(4);
    expect(series[0].source).toBe("paper_wallet");
    expect(series[0].equity).toBe(1000);
    expect(series[series.length - 1].equity).toBe(1000.16);
  });
});

describe("computeLiveSessionMetrics", () => {
  it("computes return and drawdown", () => {
    const summary = summarizeLiveJobLog(SAMPLE_LOG);
    const series = parseLiveEquitySeries(SAMPLE_LOG);
    const metrics = computeLiveSessionMetrics(summary, series);
    expect(metrics.initialCash).toBe(1000);
    expect(metrics.currentEquity).toBe(1000.16);
    expect(metrics.sessionPnl).toBeCloseTo(0.16, 2);
    expect(metrics.sessionReturnPct).toBeCloseTo(0.016, 2);
    expect(metrics.buyCount).toBe(1);
    expect(metrics.drawdownPct).toBeGreaterThan(0);
    expect(metrics.firstActivityUnix).toBe(1700000000);
  });
});

describe("countLiveFillStats", () => {
  it("counts round trips and open legs", () => {
    const stats = countLiveFillStats([
      { timestamp: 1, action: "buy", price: 100 },
      { timestamp: 2, action: "buy", price: 101 },
      { timestamp: 3, action: "sell", price: 102 },
      { timestamp: 4, action: "buy", price: 103 },
    ]);
    expect(stats.buyCount).toBe(3);
    expect(stats.sellCount).toBe(1);
    expect(stats.roundTripCount).toBe(1);
    expect(stats.openBuyLegs).toBe(2);
  });
});

describe("parseLiveTickStats", () => {
  it("counts tick statuses", () => {
    const stats = parseLiveTickStats(SAMPLE_LOG);
    expect(stats.evaluated).toBe(1);
    expect(stats.noNewBar).toBe(1);
    expect(stats.signals).toBe(1);
  });
});

describe("buyAndHoldEquity", () => {
  it("scales with price ratio", () => {
    expect(buyAndHoldEquity(1000, 100, 110)).toBe(1100);
  });
});

describe("formatLiveLogPhaseSummary", () => {
  it("shows optimizer running only while incomplete", () => {
    const running = summarizeLiveJobLog(
      '{"event":"live_tune_start","strategy":"sma_cross"}',
    );
    expect(formatLiveLogPhaseSummary(running)).toBe("Optimizer running");
  });

  it("does not show optimizer started after complete", () => {
    const log = [
      '{"event":"live_tune_start","strategy":"sma_cross"}',
      '{"event":"live_tune_sweep","status":"ok","return_pct":1.2,"holdout_return_pct":0.5}',
      '{"event":"live_tune_complete","strategy":"sma_cross"}',
      '{"terminal":"live","strategy":"sma_cross"}',
      '{"event":"tick","poll":1,"portfolio":{"quote_cash":200,"quote_currency":"usdt","base_amount":7.84,"equity":1000,"mark_price":102,"base_value":799.68}}',
    ].join("\n");
    const summary = summarizeLiveJobLog(log);
    const trace = formatLiveLogPhaseSummary(summary);
    expect(trace).not.toContain("Optimizer started");
    expect(trace).toContain("Optimized");
    expect(trace).toContain("In position");
  });
});

describe("computeLiveSessionMetrics", () => {
  it("keeps equity when quote cash is zero but base is held", () => {
    const log = [
      '{"event":"paper_wallet","initial_cash":1000,"strategy_id":"sma_cross"}',
      '{"event":"signal","action":"buy","timestamp":1700000000,"close":100,"portfolio":{"quote_cash":0,"quote_currency":"usdt","base_amount":10,"equity":1000,"mark_price":100,"base_value":1000}}',
      '{"event":"tick","poll":2,"status":"no_new_bar","portfolio":{"quote_cash":0,"quote_currency":"usdt","base_amount":10,"equity":1005,"mark_price":100.5,"base_value":1005}}',
    ].join("\n");
    const summary = summarizeLiveJobLog(log);
    const series = parseLiveEquitySeries(log);
    const metrics = computeLiveSessionMetrics(summary, series);
    expect(metrics.currentEquity).toBe(1005);
    expect(metrics.sessionReturnPct).toBeCloseTo(0.5, 1);
  });
});

describe("formatLivePositionLabel", () => {
  it("detects flat vs in position", () => {
    const flat = summarizeLiveJobLog(
      '{"event":"tick","portfolio":{"quote_cash":1000,"quote_currency":"usdt","base_amount":0,"equity":1000,"mark_price":100}}',
    );
    expect(isLiveSessionInPosition(flat)).toBe(false);
    const summary = summarizeLiveJobLog(SAMPLE_LOG);
    expect(isLiveSessionInPosition(summary)).toBe(true);
    expect(formatLivePositionLabel(summary)).toContain("In position");
  });
});

describe("trimBarsFromSessionStart", () => {
  it("trims leading bars before session", () => {
    const bars = [
      { timestamp: 1 },
      { timestamp: 2 },
      { timestamp: 100 },
      { timestamp: 101 },
    ];
    const trimmed = trimBarsFromSessionStart(bars, 100, 1);
    expect(trimmed.map((bar) => bar.timestamp)).toEqual([2, 100, 101]);
  });
});
