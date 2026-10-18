"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { MarketSearchPicker } from "@/components/MarketSearchPicker";
import { Button } from "@/components/ui/Button";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import type { DatasetRow, MarketSpec } from "@/lib/api";
import {
  datasetIdsForSymbols,
  filterOptimizerDatasets,
  resolveSingleDatasetId,
} from "@/lib/optimizerCatalog";
import {
  uniqueDatasetResolutions,
  uniqueDatasetSymbols,
} from "@/lib/dataFilters";
import { formatDurationMinutes, minutesFromResolution } from "@/lib/format";

type OptimizerDatasetSectionProps =
  | {
      datasets: DatasetRow[];
      mode: "single";
      singleDatasetId: string;
      onSingleDatasetIdChange: (id: string) => void;
    }
  | {
      datasets: DatasetRow[];
      mode: "multi";
      multiSelectedIds: Set<string>;
      onMultiSelectedIdsChange: (ids: Set<string>) => void;
    };

function MultiDatasetTable({
  rows,
  selectedIds,
  onToggle,
  onSelectAll,
  onClear,
}: {
  rows: DatasetRow[];
  selectedIds: Set<string>;
  onToggle: (id: string) => void;
  onSelectAll: () => void;
  onClear: () => void;
}) {
  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted">
        No catalog files match.{" "}
        <Link href="/data" className="text-accent hover:underline">Export on Data</Link> or change filters.
      </p>
    );
  }
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="secondary" onClick={onSelectAll}>
          Select filtered ({rows.length})
        </Button>
        <Button type="button" variant="secondary" onClick={onClear} disabled={selectedIds.size === 0}>
          Clear
        </Button>
        <span className="self-center text-xs text-muted">{selectedIds.size} selected</span>
      </div>
      <div className="max-h-48 overflow-y-auto rounded-lg border border-border bg-panel/30">
        <table className="data">
          <thead className="sticky top-0 bg-panel">
            <tr>
              <th className="w-10" />
              <th>File</th>
              <th>Symbol</th>
              <th>Interval</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className={selectedIds.has(row.id) ? "bg-accent/10" : undefined}>
                <td>
                  <input
                    type="checkbox"
                    checked={selectedIds.has(row.id)}
                    onChange={() => onToggle(row.id)}
                    aria-label={`Select ${row.label}`}
                  />
                </td>
                <td className="truncate text-sm">{row.label}</td>
                <td className="font-mono text-xs text-muted">{row.symbol ?? "—"}</td>
                <td className="text-xs text-muted">
                  {minutesFromResolution(row.resolution) != null
                    ? formatDurationMinutes(minutesFromResolution(row.resolution)!)
                    : row.resolution ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function OptimizerDatasetSection(props: OptimizerDatasetSectionProps) {
  const { datasets, mode } = props;
  const singleDatasetId = props.mode === "single" ? props.singleDatasetId : "";
  const onSingleDatasetIdChange = props.mode === "single" ? props.onSingleDatasetIdChange : () => {};
  const multiSelectedIds = props.mode === "multi" ? props.multiSelectedIds : new Set<string>();
  const onMultiSelectedIdsChange =
    props.mode === "multi" ? props.onMultiSelectedIdsChange : () => {};
  const [marketSymbol, setMarketSymbol] = useState<string | null>(null);
  const [batchMarketSymbols, setBatchMarketSymbols] = useState<string[]>([]);
  const [catalogSearch, setCatalogSearch] = useState("");
  const [catalogResolution, setCatalogResolution] = useState("");

  const symbolFilter = mode === "multi" && batchMarketSymbols.length > 0 ? null : marketSymbol;
  const filtered = useMemo(
    () =>
      filterOptimizerDatasets(datasets, {
        search: catalogSearch,
        symbol: symbolFilter,
        resolution: catalogResolution,
      }),
    [datasets, catalogSearch, symbolFilter, catalogResolution],
  );

  const multiFiltered = useMemo(() => {
    if (mode !== "multi" || batchMarketSymbols.length === 0) {
      return filtered;
    }
    const set = new Set(batchMarketSymbols);
    return filtered.filter((row) => row.symbol && set.has(row.symbol));
  }, [batchMarketSymbols, filtered, mode]);

  const resolutionOptions = useMemo(() => uniqueDatasetResolutions(datasets), [datasets]);
  const symbolOptions = useMemo(() => uniqueDatasetSymbols(datasets), [datasets]);

  useEffect(() => {
    if (mode !== "single") {
      return;
    }
    const next = resolveSingleDatasetId(filtered, singleDatasetId);
    if (next !== singleDatasetId) {
      onSingleDatasetIdChange(next);
    }
  }, [filtered, mode, onSingleDatasetIdChange, singleDatasetId]);

  function selectMarket(market: MarketSpec) {
    setMarketSymbol(market.symbol);
    if (mode === "single") {
      const forSymbol = filterOptimizerDatasets(datasets, {
        search: catalogSearch,
        symbol: market.symbol,
        resolution: catalogResolution,
      });
      onSingleDatasetIdChange(resolveSingleDatasetId(forSymbol, singleDatasetId));
    }
  }

  function toggleBatchMarket(market: MarketSpec) {
    setBatchMarketSymbols((previous) => {
      if (previous.includes(market.symbol)) {
        return previous.filter((item) => item !== market.symbol);
      }
      return [...previous, market.symbol];
    });
    setMarketSymbol(market.symbol);
  }

  function selectFilesForBatchMarkets() {
    const ids = datasetIdsForSymbols(datasets, batchMarketSymbols);
    if (ids.length === 0) {
      return;
    }
    onMultiSelectedIdsChange(new Set(ids));
  }

  function toggleMulti(id: string) {
    onMultiSelectedIdsChange(
      new Set(
        multiSelectedIds.has(id)
          ? [...multiSelectedIds].filter((item) => item !== id)
          : [...multiSelectedIds, id],
      ),
    );
  }

  const displayRows = mode === "multi" ? multiFiltered : filtered;

  return (
    <section className="panel-inset space-y-4">
      <div>
        <h3 className="text-sm font-medium text-white">Market search</h3>
        <p className="mt-1 text-xs text-muted">
          {mode === "single"
            ? "Find a pair in the exchange catalog, then pick the OHLC file to optimize."
            : "Search markets to filter files, or check several markets and add all matching catalog CSVs."}
        </p>
      </div>

      <MarketSearchPicker
        selectedSymbol={marketSymbol}
        onSelect={selectMarket}
        batchMode={mode === "multi"}
        batchSymbols={batchMarketSymbols}
        onToggleBatch={toggleBatchMarket}
        onClearBatch={() => setBatchMarketSymbols([])}
        maxBatchSelect={32}
      />

      {mode === "multi" && batchMarketSymbols.length > 0 && (
        <Button type="button" variant="secondary" onClick={selectFilesForBatchMarkets}>
          Select all catalog files for {batchMarketSymbols.length} market
          {batchMarketSymbols.length === 1 ? "" : "s"}
        </Button>
      )}

      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Filter files" hint="Label, path, symbol…">
          <TextInput
            placeholder="e.g. btc, 15, export"
            value={catalogSearch}
            onChange={(event) => setCatalogSearch(event.target.value)}
            autoComplete="off"
          />
        </Field>
        <Field label="Symbol (catalog)">
          <SelectInput
            value={marketSymbol ?? ""}
            onChange={(event) => {
              const value = event.target.value;
              setMarketSymbol(value || null);
            }}
          >
            <option value="">All symbols</option>
            {symbolOptions.map((symbol) => (
              <option key={symbol} value={symbol}>
                {symbol}
              </option>
            ))}
          </SelectInput>
        </Field>
        <Field label="Interval">
          <SelectInput
            value={catalogResolution}
            onChange={(event) => setCatalogResolution(event.target.value)}
          >
            <option value="">All intervals</option>
            {resolutionOptions.map((resolution) => (
              <option key={resolution} value={resolution}>
                {resolution}
                {minutesFromResolution(resolution) != null
                  ? ` (${formatDurationMinutes(minutesFromResolution(resolution)!)})`
                  : ""}
              </option>
            ))}
          </SelectInput>
        </Field>
      </div>

      {mode === "single" ? (
        <Field
          label="OHLC file"
          hint={
            displayRows.length > 0
              ? `${displayRows.length} file${displayRows.length === 1 ? "" : "s"} match filters`
              : "No files match — export data or relax filters"
          }
        >
          <SelectInput
            value={singleDatasetId}
            onChange={(event) => onSingleDatasetIdChange(event.target.value)}
            disabled={displayRows.length === 0}
          >
            {displayRows.map((dataset) => (
              <option key={dataset.id} value={dataset.id}>
                {dataset.label}
              </option>
            ))}
          </SelectInput>
        </Field>
      ) : (
        <Field label="Catalog files">
          <MultiDatasetTable
            rows={displayRows}
            selectedIds={multiSelectedIds}
            onToggle={toggleMulti}
            onSelectAll={() => onMultiSelectedIdsChange(new Set(displayRows.map((row) => row.id)))}
            onClear={() => onMultiSelectedIdsChange(new Set())}
          />
        </Field>
      )}
    </section>
  );
}
