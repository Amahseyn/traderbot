import { describe, expect, it } from "vitest";
import { estimateDiscoveryCredits } from "@/lib/discoveryCredits";

describe("estimateDiscoveryCredits", () => {
  it("matches coinbeacon_run formula", () => {
    expect(
      estimateDiscoveryCredits({
        screenerPresetCount: 15,
        includeContext: true,
        detailTopN: 12,
      }),
    ).toBe(5 + 15 * 5 + 3 + 12);
  });
});
