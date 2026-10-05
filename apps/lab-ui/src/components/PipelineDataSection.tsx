"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo } from "react";
import { Button } from "@/components/ui/Button";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import { api, datasetDownloadUrl, type DatasetRow } from "@/lib/api";
import {
  datasetMatchesFilters,
  marketMatchesSearch,
  type MarketScope,
  uniqueDatasetResolutions,
  uniqueDatasetSymbols,
} from "@/lib/dataFilters";
import { formatDurationMinutes, formatUtcTimestamp, minutesFromResolution } from "@/lib/format";

export type DataSourceMode = "existing" | "download";

export type PipelineDataSectionState = {
  dataSourceMode: DataSourceMode;
  exportDays: string;
  exportMarketSymbol: string;
  exportInterval: string;
  useAllHourly: boolean;
  datasetIds: string[];
  catalogSearch: string;
  catalogSymbol: string;
  catalogResolution: string;
  marketScope: MarketScope;
  marketSearch: string;
};

type PipelineDataSectionProps = {
  state: PipelineDataSectionState;
  onChange: (patch: Partial<PipelineDataSectionState>) => void;
  onExportJobStarted?: (jobId: string) => void;
};

function CatalogDatasetTable({
  rows,
  selectedIds,
  onToggle,
  onSelectFiltered,
  onClear,
}: {
  rows: DatasetRow[];
  selectedIds: string[];
  onToggle: (id: string) => void;
  onSelectFiltered: () => void;
  onClear: () => void;
}) {
  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted">
        No datasets match these filters.{" "}
        <Link href="/data" className="text-accent hover:underline">
          Export OHLC on Data
        </Link>{" "}
        or switch to download before run.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="secondary" onClick={onSelectFiltered}>
          Select filtered ({rows.length})
        </Button>
        <Button type="button" variant="secondary" onClick={onClear} disabled={selectedIds.length === 0}>
          Clear selection
        </Button>
        <span className="self-center text-xs text-muted">{selectedIds.length} selected</span>
      </div>
      <div className="max-h-56 overflow-auto rounded-lg border border-border">
        <table className="data">
          <thead className="sticky top-0 bg-panel">
            <tr>
              <th />
              <th>File</th>
              <th>Symbol</th>
              <th>Interval</th>
              <th>Range</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((dataset) => {
              const minutes = minutesFromResolution(dataset.resolution);
              const checked = selectedIds.includes(dataset.id);
              return (
                <tr key={dataset.id} className={checked ? "bg-accent/10" : undefined}>
                  <td>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => onToggle(dataset.id)}
                      aria-label={`Select ${dataset.label}`}
                    />
                  </td>
                  <td className="text-sm">{dataset.label}</td>
                  <td className="font-mono text-xs text-muted">{dataset.symbol ?? "—"}</td>
                  <td className="text-xs text-muted">
                    {minutes != null ? formatDurationMinutes(minutes) : dataset.resolution ?? "—"}
                  </td>
                  <td className="text-xs text-muted">
                    {dataset.range_start_utc && dataset.range_end_utc
                      ? `${dataset.range_start_utc.slice(0, 10)} … ${dataset.range_end_utc.slice(0, 10)}`
                      : "—"}
                  </td>
                  <td>
                    <a
                      href={datasetDownloadUrl(dataset.id)}
                      className="text-xs text-accent hover:underline"
                    >
                      CSV
                    </a>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function PipelineDataSection({ state, onChange, onExportJobStarted }: PipelineDataSectionProps) {
  const queryClient = useQueryClient();

  const datasetsQuery = useQuery({
    queryKey: ["datasets"],
    queryFn: () => api.datasets(500),
  });

  const catalogQuery = useQuery({
    queryKey: ["data-markets-catalog", state.marketScope],
    queryFn: () => api.dataMarketsCatalog(state.marketScope),
    staleTime: 60_000,
  });

  const syncMarketsMutation = useMutation({
    mutationFn: () => api.syncMarkets(state.marketScope),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["data-markets-catalog"] });
    },
  });

  const standaloneExportMutation = useMutation({
    mutationFn: () =>
      api.postJob("export", {
        market_symbol: state.exportMarketSymbol,
        interval: state.exportInterval,
        days: Number(state.exportDays),
        out: "data",
      }),
    onSuccess: (data) => {
      onExportJobStarted?.(data.id);
      void queryClient.invalidateQueries({ queryKey: ["datasets"] });
    },
  });

  const allDatasets = datasetsQuery.data ?? [];
  const symbolOptions = useMemo(() => uniqueDatasetSymbols(allDatasets), [allDatasets]);
  const resolutionOptions = useMemo(() => uniqueDatasetResolutions(allDatasets), [allDatasets]);

  const filteredDatasets = useMemo(
    () =>
      allDatasets.filter((dataset) =>
        datasetMatchesFilters(dataset, {
          search: state.catalogSearch,
          symbol: state.catalogSymbol,
          resolution: state.catalogResolution,
        }),
      ),
    [allDatasets, state.catalogSearch, state.catalogSymbol, state.catalogResolution],
  );

  const searchNeedle = state.marketSearch.trim().toLowerCase();
  const allMarkets = catalogQuery.data?.markets ?? [];
  const filteredMarkets = useMemo(
    () => allMarkets.filter((market) => marketMatchesSearch(market, searchNeedle)),
    [allMarkets, searchNeedle],
  );
  const resolutions = catalogQuery.data?.udf_resolutions ?? ["1", "15", "60", "D"];
  const totalInCatalog = catalogQuery.data?.total_in_catalog ?? 0;
  const catalogEmpty = !catalogQuery.isLoading && totalInCatalog === 0;

  function toggleDataset(id: string) {
    if (state.datasetIds.includes(id)) {
      onChange({ datasetIds: state.datasetIds.filter((item) => item !== id) });
    } else {
      onChange({ datasetIds: [...state.datasetIds, id] });
    }
  }

  function selectAllFiltered() {
    const ids = new Set(state.datasetIds);
    for (const dataset of filteredDatasets) {
      ids.add(dataset.id);
    }
    onChange({ datasetIds: [...ids] });
  }

  return (
    <div className="space-y-5">
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium text-slate-200">Data source</legend>
        <div className="flex flex-wrap gap-4 text-sm text-slate-200">
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name="data-source-mode"
              checked={state.dataSourceMode === "existing"}
              onChange={() => onChange({ dataSourceMode: "existing" })}
            />
            Use existing catalog
          </label>
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name="data-source-mode"
              checked={state.dataSourceMode === "download"}
              onChange={() => onChange({ dataSourceMode: "download" })}
            />
            Download before this run
          </label>
        </div>
      </fieldset>

      {state.dataSourceMode === "existing" && (
        <section className="panel-inset space-y-4">
          <p className="text-xs text-muted">
            Filter registered OHLC files, then select one or more for strategy compare and forecasts.
          </p>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Search" hint="Label, symbol, path…">
              <TextInput
                placeholder="e.g. btc, 60, export"
                value={state.catalogSearch}
                onChange={(event) => onChange({ catalogSearch: event.target.value })}
                autoComplete="off"
              />
            </Field>
            <Field label="Symbol">
              <SelectInput
                value={state.catalogSymbol}
                onChange={(event) => onChange({ catalogSymbol: event.target.value })}
              >
                <option value="">All symbols</option>
                {symbolOptions.map((symbol) => (
                  <option key={symbol} value={symbol}>
                    {symbol}
                  </option>
                ))}
              </SelectInput>
            </Field>
            <Field label="Resolution">
              <SelectInput
                value={state.catalogResolution}
                onChange={(event) => onChange({ catalogResolution: event.target.value })}
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
          {datasetsQuery.isLoading && <p className="text-sm text-muted">Loading datasets…</p>}
          {datasetsQuery.isError && (
            <p className="text-sm text-red-400">
              {datasetsQuery.error instanceof Error ? datasetsQuery.error.message : "Could not load datasets."}
            </p>
          )}
          {!datasetsQuery.isLoading && (
            <CatalogDatasetTable
              rows={filteredDatasets}
              selectedIds={state.datasetIds}
              onToggle={toggleDataset}
              onSelectFiltered={selectAllFiltered}
              onClear={() => onChange({ datasetIds: [] })}
            />
          )}
          <label className="flex items-center gap-2 text-sm text-slate-200">
            <input
              type="checkbox"
              checked={state.useAllHourly}
              onChange={(event) => onChange({ useAllHourly: event.target.checked })}
            />
            Also include every hourly file under data/ (*_60.csv)
          </label>
        </section>
      )}

      {state.dataSourceMode === "download" && (
        <section className="panel-inset space-y-4">
          <p className="text-xs text-muted">
            Pick a Nobitex market and interval. The pipeline exports OHLC as part of the same job (or run a
            standalone export below).
          </p>
          <div className="max-w-xs">
            <Field label="History (days)">
              <TextInput
                type="number"
                min={1}
                value={state.exportDays}
                onChange={(event) => onChange({ exportDays: event.target.value })}
              />
            </Field>
          </div>
          <>
              <div className="flex flex-wrap items-end gap-3">
                <Field label="Catalog scope">
                  <SelectInput
                    value={state.marketScope}
                    onChange={(event) => {
                      onChange({
                        marketScope: event.target.value as MarketScope,
                        exportMarketSymbol: "",
                        marketSearch: "",
                      });
                    }}
                  >
                    <option value="nobitex_all">All Nobitex (cloned)</option>
                    <option value="default_jobs">Crypto 1h jobs file</option>
                  </SelectInput>
                </Field>
                <Field label="Search markets">
                  <TextInput
                    placeholder="btc, eth/usdt…"
                    value={state.marketSearch}
                    onChange={(event) => onChange({ marketSearch: event.target.value })}
                    disabled={catalogEmpty}
                    autoComplete="off"
                  />
                </Field>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={syncMarketsMutation.isPending}
                  onClick={() => syncMarketsMutation.mutate()}
                >
                  {syncMarketsMutation.isPending ? "Syncing…" : "Sync catalog"}
                </Button>
              </div>

              {catalogQuery.isLoading && <p className="text-sm text-muted">Loading market catalog…</p>}
              {catalogEmpty && (
                <p className="text-sm text-muted">Sync the catalog first, then pick a market for export.</p>
              )}

              {totalInCatalog > 0 && (
                <>
                  <p className="text-xs text-muted">
                    {filteredMarkets.length.toLocaleString()} shown
                    {searchNeedle ? ` of ${totalInCatalog.toLocaleString()}` : ""}
                    {catalogQuery.data?.updated_at_utc
                      ? ` · synced ${formatUtcTimestamp(catalogQuery.data.updated_at_utc)}`
                      : ""}
                  </p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="Market">
                      <SelectInput
                        value={state.exportMarketSymbol}
                        onChange={(event) => onChange({ exportMarketSymbol: event.target.value })}
                      >
                        <option value="">Select market…</option>
                        {state.exportMarketSymbol &&
                          !filteredMarkets.some((market) => market.symbol === state.exportMarketSymbol) && (
                            <option value={state.exportMarketSymbol}>{state.exportMarketSymbol}</option>
                          )}
                        {filteredMarkets.slice(0, 300).map((market) => (
                          <option key={market.symbol} value={market.symbol}>
                            {market.label} ({market.symbol})
                          </option>
                        ))}
                      </SelectInput>
                    </Field>
                    <Field label="Interval">
                      <SelectInput
                        value={state.exportInterval}
                        onChange={(event) => onChange({ exportInterval: event.target.value })}
                      >
                        {resolutions.map((resolution) => (
                          <option key={resolution} value={resolution}>
                            {resolution}
                          </option>
                        ))}
                      </SelectInput>
                    </Field>
                  </div>
                  <div className="max-h-40 overflow-auto rounded-lg border border-border">
                    <table className="data">
                      <thead className="sticky top-0 bg-panel">
                        <tr>
                          <th>Pair</th>
                          <th>Symbol</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {filteredMarkets.slice(0, 80).map((market) => (
                          <tr
                            key={market.symbol}
                            className={
                              market.symbol === state.exportMarketSymbol ? "bg-accent/10" : undefined
                            }
                          >
                            <td>{market.label}</td>
                            <td className="font-mono text-xs">{market.symbol}</td>
                            <td>
                              <button
                                type="button"
                                className="text-xs text-accent hover:underline"
                                onClick={() => onChange({ exportMarketSymbol: market.symbol })}
                              >
                                Select
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}

              <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs text-muted">
                <p>
                  The custom pipeline exports this market as part of the same job. You can also{" "}
                  <button
                    type="button"
                    className="text-accent hover:underline"
                    disabled={!state.exportMarketSymbol || standaloneExportMutation.isPending}
                    onClick={() => standaloneExportMutation.mutate()}
                  >
                    run a standalone export
                  </button>{" "}
                  and switch to “Use existing catalog” after it finishes.
                </p>
                {standaloneExportMutation.isError && (
                  <p className="mt-1 text-red-400">
                    {standaloneExportMutation.error instanceof Error
                      ? standaloneExportMutation.error.message
                      : "Export failed to start."}
                  </p>
                )}
              </div>
          </>

          <details className="text-sm text-muted">
            <summary className="cursor-pointer text-slate-200">Also use catalog files (optional)</summary>
            <div className="mt-3 space-y-3">
              <div className="grid gap-3 sm:grid-cols-3">
                <Field label="Search">
                  <TextInput
                    value={state.catalogSearch}
                    onChange={(event) => onChange({ catalogSearch: event.target.value })}
                  />
                </Field>
                <Field label="Symbol">
                  <SelectInput
                    value={state.catalogSymbol}
                    onChange={(event) => onChange({ catalogSymbol: event.target.value })}
                  >
                    <option value="">All</option>
                    {symbolOptions.map((symbol) => (
                      <option key={symbol} value={symbol}>{symbol}</option>
                    ))}
                  </SelectInput>
                </Field>
                <Field label="Resolution">
                  <SelectInput
                    value={state.catalogResolution}
                    onChange={(event) => onChange({ catalogResolution: event.target.value })}
                  >
                    <option value="">All</option>
                    {resolutionOptions.map((resolution) => (
                      <option key={resolution} value={resolution}>{resolution}</option>
                    ))}
                  </SelectInput>
                </Field>
              </div>
              <CatalogDatasetTable
                rows={filteredDatasets}
                selectedIds={state.datasetIds}
                onToggle={toggleDataset}
                onSelectFiltered={selectAllFiltered}
                onClear={() => onChange({ datasetIds: [] })}
              />
              <label className="flex items-center gap-2 text-sm text-slate-200">
                <input
                  type="checkbox"
                  checked={state.useAllHourly}
                  onChange={(event) => onChange({ useAllHourly: event.target.checked })}
                />
                Include all hourly files (*_60.csv)
              </label>
            </div>
          </details>
        </section>
      )}
    </div>
  );
}

export function pipelineDataSourceReady(state: PipelineDataSectionState): boolean {
  if (state.dataSourceMode === "download") {
    if (state.exportMarketSymbol.trim()) {
      return true;
    }
    return state.useAllHourly || state.datasetIds.length > 0;
  }
  return state.useAllHourly || state.datasetIds.length > 0;
}
