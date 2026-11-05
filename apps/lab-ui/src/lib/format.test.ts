import { describe, expect, it } from "vitest";
import {
  formatBps,
  formatCompact,
  formatCryptoPrice,
  formatPct,
  returnPctClassName,
} from "@/lib/format";

describe("formatCryptoPrice", () => {
  it("formats high-value assets with standard 2 decimal places and thousands separators", () => {
    expect(formatCryptoPrice(95420.5)).toBe("$95,420.50");
    expect(formatCryptoPrice(1000)).toBe("$1,000.00");
  });

  it("formats mid-tier prices with 2 to 4 decimal places", () => {
    expect(formatCryptoPrice(3.1415)).toBe("$3.1415");
    expect(formatCryptoPrice(12.5)).toBe("$12.50");
  });

  it("formats cents and sub-cents with magnitude-aware precision", () => {
    expect(formatCryptoPrice(0.0456)).toBe("$0.0456");
    expect(formatCryptoPrice(0.000123)).toBe("$0.000123");
    expect(formatCryptoPrice(0.00000456)).toBe("$0.00000456");
  });

  it("handles null and undefined gracefully", () => {
    expect(formatCryptoPrice(null)).toBe("—");
    expect(formatCryptoPrice(undefined)).toBe("—");
  });

  it("supports custom currency prefixes", () => {
    expect(formatCryptoPrice(1500, "USDT ")).toBe("USDT 1,500.00");
  });
});

describe("formatCompact", () => {
  it("formats trillions, billions, millions, and thousands", () => {
    expect(formatCompact(2.45e12)).toBe("$2.45T");
    expect(formatCompact(1.23e9)).toBe("$1.23B");
    expect(formatCompact(45.67e6)).toBe("$45.67M");
    expect(formatCompact(12.5e3)).toBe("$12.5K");
    expect(formatCompact(500)).toBe("$500");
  });

  it("handles empty values", () => {
    expect(formatCompact(null)).toBe("—");
    expect(formatCompact(undefined)).toBe("—");
  });
});

describe("formatBps", () => {
  it("formats basis points under 100 as bps", () => {
    expect(formatBps(15.5)).toBe("15.5 bps");
    expect(formatBps(-5.2)).toBe("-5.2 bps");
  });

  it("converts basis points >= 100 to percentages", () => {
    expect(formatBps(150)).toBe("1.50%");
    expect(formatBps(-200)).toBe("-2.00%");
  });

  it("handles empty values", () => {
    expect(formatBps(null)).toBe("—");
  });
});

describe("formatPct", () => {
  it("formats percentages with explicit plus for positive", () => {
    expect(formatPct(5.25)).toBe("+5.25%");
    expect(formatPct(-3.1)).toBe("-3.10%");
    expect(formatPct(0)).toBe("0.00%");
  });

  it("allows suppressing explicit plus", () => {
    expect(formatPct(5.25, 2, false)).toBe("5.25%");
  });
});

describe("returnPctClassName", () => {
  it("returns semantic tokens for positive and negative returns", () => {
    expect(returnPctClassName(1.5)).toBe("text-positive");
    expect(returnPctClassName(-0.8)).toBe("text-negative");
    expect(returnPctClassName(0)).toBe("text-muted");
    expect(returnPctClassName(null)).toBe("text-muted");
  });
});

