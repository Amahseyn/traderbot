import { describe, expect, it } from "vitest";
import type { DatasetRow } from "@/lib/api";
import {
  datasetIdsForSymbols,
  filterOptimizerDatasets,
  resolveSingleDatasetId,
} from "@/lib/optimizerCatalog";

const rows: DatasetRow[] = [
  {
    id: "a",
    label: "BTC 1h",
    symbol: "BTCUSDT",
    resolution: "60",
    horizon_label: null,
    range_start_utc: null,
    range_end_utc: null,
    source: "export",
    repo_path: "data/btc_60.csv",
    last_seen_at_utc: "2026-01-01T00:00:00Z",
  },
  {
    id: "b",
    label: "ETH 1h",
    symbol: "ETHUSDT",
    resolution: "60",
    horizon_label: null,
    range_start_utc: null,
    range_end_utc: null,
    source: "export",
    repo_path: "data/eth_60.csv",
    last_seen_at_utc: "2026-01-01T00:00:00Z",
  },
];

describe("optimizerCatalog", () => {
  it("filters by symbol", () => {
    const filtered = filterOptimizerDatasets(rows, { search: "", symbol: "BTCUSDT", resolution: "" });
    expect(filtered.map((row) => row.id)).toEqual(["a"]);
  });

  it("resolves single dataset id when current is missing from filter", () => {
    expect(resolveSingleDatasetId(rows, "missing")).toBe("a");
    expect(resolveSingleDatasetId([rows[1]], "a")).toBe("b");
  });

  it("collects dataset ids for symbols", () => {
    expect(datasetIdsForSymbols(rows, ["ETHUSDT", "BTCUSDT"]).sort()).toEqual(["a", "b"]);
  });
});
