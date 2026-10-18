import { describe, expect, it } from "vitest";

import {
  filterStrategies,
  selectionCountLabel,
  strategyMatchesQuery,
  strategyStyleLabel,
  strategyStyles,
  toggleStyle,
  visibleStrategyIds,
} from "@/lib/strategySelection";

const catalog = [
  { id: "sma_cross", name: "SMA Cross", style: "trend", summary: "Fast/slow moving-average crossover" },
  { id: "rsi_reversion", name: "RSI Reversion", style: "mean_reversion", summary: "Buy oversold" },
  { id: "bollinger", name: "Bollinger Bands", style: "mean_reversion", summary: "Band reversion" },
  { id: "donchian", name: "Donchian Breakout", style: "breakout", summary: "Channel breakout" },
  { id: "ml_alpha", name: "ML Alpha", style: "ml", summary: "Gradient boosting" },
];

describe("strategyStyleLabel", () => {
  it("maps known styles to friendly labels", () => {
    expect(strategyStyleLabel("trend")).toBe("Trend");
    expect(strategyStyleLabel("mean_reversion")).toBe("Mean reversion");
    expect(strategyStyleLabel("ml")).toBe("ML");
  });

  it("title-cases unknown styles and handles blanks", () => {
    expect(strategyStyleLabel("custom_thing")).toBe("Custom Thing");
    expect(strategyStyleLabel("")).toBe("Other");
    expect(strategyStyleLabel(null)).toBe("Other");
  });
});

describe("strategyStyles", () => {
  it("dedupes and orders styles by the preferred order", () => {
    expect(strategyStyles(catalog)).toEqual(["trend", "mean_reversion", "breakout", "ml"]);
  });

  it("appends unknown styles alphabetically", () => {
    const rows = [...catalog, { id: "x", style: "zzz" }, { id: "y", style: "aaa" }];
    expect(strategyStyles(rows).slice(-2)).toEqual(["aaa", "zzz"]);
  });

  it("ignores missing styles", () => {
    expect(strategyStyles([{ id: "a", style: null }, { id: "b" }])).toEqual([]);
  });
});

describe("strategyMatchesQuery", () => {
  it("matches id, name, summary and style label", () => {
    expect(strategyMatchesQuery(catalog[0], "sma")).toBe(true);
    expect(strategyMatchesQuery(catalog[0], "cross")).toBe(true);
    expect(strategyMatchesQuery(catalog[0], "moving-average")).toBe(true);
    expect(strategyMatchesQuery(catalog[0], "trend")).toBe(true);
    expect(strategyMatchesQuery(catalog[0], "zzz")).toBe(false);
  });

  it("treats blank queries as match-all", () => {
    expect(strategyMatchesQuery(catalog[0], "   ")).toBe(true);
  });
});

describe("filterStrategies", () => {
  it("returns everything with an empty filter", () => {
    expect(filterStrategies(catalog, { query: "", styles: [] })).toHaveLength(catalog.length);
  });

  it("filters by style (OR within styles)", () => {
    const rows = filterStrategies(catalog, { query: "", styles: ["mean_reversion", "breakout"] });
    expect(rows.map((row) => row.id)).toEqual(["rsi_reversion", "bollinger", "donchian"]);
  });

  it("combines style and query filters", () => {
    const rows = filterStrategies(catalog, { query: "band", styles: ["mean_reversion"] });
    expect(rows.map((row) => row.id)).toEqual(["bollinger"]);
  });

  it("is case-insensitive for style filters", () => {
    expect(filterStrategies(catalog, { query: "", styles: ["TREND"] })).toHaveLength(1);
  });
});

describe("toggleStyle", () => {
  it("adds and removes styles without mutating the input", () => {
    const original: string[] = ["trend"];
    const added = toggleStyle(original, "ml");
    expect(added).toEqual(["trend", "ml"]);
    expect(original).toEqual(["trend"]);
    expect(toggleStyle(added, "ml")).toEqual(["trend"]);
  });

  it("normalizes the toggled style", () => {
    expect(toggleStyle([], "ML")).toEqual(["ml"]);
  });
});

describe("selectionCountLabel / visibleStrategyIds", () => {
  it("labels the selected count", () => {
    expect(selectionCountLabel(3, 18)).toBe("3 of 18 selected");
    expect(selectionCountLabel(0, 5)).toBe("0 of 5 selected");
  });

  it("returns ids visible under the filter", () => {
    expect(visibleStrategyIds(catalog, { query: "", styles: ["ml"] })).toEqual(["ml_alpha"]);
  });
});
