import { describe, expect, it } from "vitest";
import { extractDiscoveryErrorLogLines } from "@/lib/opportunityDiscoveryLog";

describe("extractDiscoveryErrorLogLines", () => {
  it("collects discovery ERROR lines and lab tracebacks", () => {
    const log = [
      "discovery: [1/1] btc 60 sma_cross",
      "discovery: ERROR btc 60 sma_cross: ValueError: bad params",
      "discovery: 1 evaluation error(s) — details above and in report rejected[]",
      "discovery: wrote results/discovery/x/discovery_report.json",
    ].join("\n");
    expect(extractDiscoveryErrorLogLines(log)).toEqual([
      "discovery: ERROR btc 60 sma_cross: ValueError: bad params",
      "discovery: 1 evaluation error(s) — details above and in report rejected[]",
    ]);
  });

  it("includes traceback after [lab] job failure", () => {
    const log = "task: opportunity-discovery\n[lab] ClientError: rate limited\nTraceback (most recent call last):\n  File \"run.py\", line 1\nClientError: 429";
    expect(extractDiscoveryErrorLogLines(log)).toContain("[lab] ClientError: rate limited");
    expect(extractDiscoveryErrorLogLines(log).some((line) => line.includes("Traceback"))).toBe(true);
  });
});
