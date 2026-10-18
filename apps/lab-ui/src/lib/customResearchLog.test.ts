import { describe, expect, it } from "vitest";

import { parseCustomResearchJobSummary } from "@/lib/customResearchLog";

describe("parseCustomResearchJobSummary", () => {
  it("reads compare benchmarks from the final summary JSON line", () => {
    const log = `
custom: compare done
{"compare": [{"csv": "/data/BTCUSDT_60.csv", "best_strategy_id": "sma_cross", "best_return_pct": -2.1, "buy_and_hold_return_pct": -5.0, "strategies_count": 12, "strategies_beat_buy_hold": 4}]}
`;
    const summary = parseCustomResearchJobSummary(log);
    expect(summary?.compare).toHaveLength(1);
    expect(summary?.compare[0].buy_and_hold_return_pct).toBe(-5);
    expect(summary?.compare[0].strategies_beat_buy_hold).toBe(4);
  });
});
