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
  exportDaysByInterval: Record<string, string>;
  exportHistoryMode: "days" | "steps";
  exportSteps: string;
  exportStepsByInterval: Record<string, string>;
  exportMarketSymbol: string;
  exportInterval: string;
  exportMarketSymbols: string[];
  exportIntervals: string[];
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
    enabled: state.dataSourceMode === "download",
  });

  const searchNeedle = state.marketSearch.trim();
  const marketsSearchQuery = useQuery({
    queryKey: ["data-markets-search", state.marketScope, searchNeedle],
    queryFn: () =>
      api.dataMarkets({
        scope: state.marketScope,
        q: searchNeedle || undefined,
        limit: 500,
      }),
    enabled: state.dataSourceMode === "download" && searchNeedle.length > 0,
    staleTime: 30_000,
  });

  const syncMarketsMutation = useMutation({
    mutationFn: (scope?: MarketScope) => api.syncMarkets(scope ?? state.marketScope),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["data-markets-catalog"] });
      queryClient.invalidateQueries({ queryKey: ["data-markets-search"] });
    },
  });

  function exportComboDays(interval: string): number {
    if (state.exportHistoryMode === "steps") {
      const rawSteps = state.exportStepsByInterval[interval] || state.exportSteps;
      const steps = Number(rawSteps);
      const minutes = minutesFromResolution(interval);
      if (Number.isFinite(steps) && steps > 0 && minutes != null && minutes > 0) {
        return Math.ceil((steps * minutes) / 1440) + 1;
      }
    } else {
      const override = state.exportDaysByInterval[interval];
      if (override != null && override.trim() !== "") {
        return Number(override);
      }
    }
    return Number(state.exportDays);
  }

  const standaloneExportMutation = useMutation({
    mutationFn: async () => {
      const symbols =
        state.exportMarketSymbols.length > 0
          ? state.exportMarketSymbols
          : state.exportMarketSymbol.trim()
            ? [state.exportMarketSymbol.trim()]
            : [];
      const intervals =
        state.exportIntervals.length > 0 ? state.exportIntervals : [state.exportInterval || "60"];
      const combos = symbols
        .flatMap((symbol) =>
          intervals.map((interval) => ({
            symbol,
            interval,
            days: exportComboDays(interval),
          })),
        )
        .slice(0, 24);
      if (combos.length === 0) {
        throw new Error("Select at least one market for export.");
      }
      let firstId = "";
      for (const combo of combos) {
        const job = await api.postJob("export", {
          market_symbol: combo.symbol,
          interval: combo.interval,
          days: combo.days,
          out: "data",
        });
        if (!firstId) firstId = job.id;
      }
      return { id: firstId, count: combos.length };
    },
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

  const searchNeedleLower = searchNeedle.toLowerCase();
  const allMarkets = catalogQuery.data?.markets ?? [];
  const filteredMarkets = useMemo(
    () => allMarkets.filter((market) => marketMatchesSearch(market, searchNeedleLower)),
    [allMarkets, searchNeedleLower],
  );
  const displayMarkets = useMemo(() => {
    if (searchNeedle.length > 0) {
      return marketsSearchQuery.data?.markets ?? [];
    }
    return filteredMarkets;
  }, [searchNeedle, marketsSearchQuery.data?.markets, filteredMarkets]);
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
            Filter registered OHLC files, then select one or more for strategy compare.
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
            Pick Nobitex markets and horizons below. The pipeline exports every combination as part of the
            same job (or run a standalone export below).
          </p>
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium text-slate-200">History size</legend>
            <div className="flex flex-wrap gap-4 text-sm text-slate-200">
              <label className="flex items-center gap-2">
                <input
                  type="radio"
                  name="export-history-mode"
                  checked={state.exportHistoryMode === "days"}
                  onChange={() => onChange({ exportHistoryMode: "days" })}
                />
                Days per horizon
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="radio"
                  name="export-history-mode"
                  checked={state.exportHistoryMode === "steps"}
                  onChange={() => onChange({ exportHistoryMode: "steps" })}
                />
                Steps (bars) per horizon
              </label>
            </div>
          </fieldset>
          {state.exportHistoryMode === "days" ? (
            <div className="max-w-xs">
              <Field
                label="Default history (days)"
                hint="Applies to every horizon unless overridden per horizon below."
              >
                <TextInput
                  type="number"
                  min={1}
                  value={state.exportDays}
                  onChange={(event) => onChange({ exportDays: event.target.value })}
                />
              </Field>
            </div>
          ) : (
            <div className="max-w-xs">
              <Field
                label="Default steps (bars)"
                hint="Same bar count for every horizon (e.g. 500 × 15m and 500 × 1h). Files are trimmed to the last N bars."
              >
                <TextInput
                  type="number"
                  min={1}
                  value={state.exportSteps}
                  onChange={(event) => onChange({ exportSteps: event.target.value })}
                />
              </Field>
            </div>
          )}
          <>
              <div className="flex flex-wrap items-end gap-3">
                <Field label="Catalog scope">
                  <SelectInput
                    value={state.marketScope}
                    onChange={(event) => {
                      onChange({
                        marketScope: event.target.value as MarketScope,
                        exportMarketSymbol: "",
                        exportMarketSymbols: [],
                        marketSearch: "",
                      });
                    }}
                  >
                    <option value="nobitex_all">All Nobitex (cloned)</option>
                    <option value="default_jobs">Crypto 1h jobs file</option>
                  </SelectInput>
                </Field>
                <Field label="Search markets" hint="Filters the catalog; works after Sync (or when the API has seeded markets).">
                  <TextInput
                    placeholder="btc, eth/usdt…"
                    value={state.marketSearch}
                    onChange={(event) => onChange({ marketSearch: event.target.value })}
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
                {state.marketScope === "nobitex_all" && (
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={syncMarketsMutation.isPending}
                    onClick={() => {
                      onChange({ marketScope: "default_jobs", marketSearch: "" });
                      syncMarketsMutation.mutate("default_jobs");
                    }}
                  >
                    Load offline catalog
                  </Button>
                )}
              </div>

              {catalogQuery.isLoading && <p className="text-sm text-muted">Loading market catalog…</p>}
              {catalogQuery.isError && (
                <p className="text-sm text-red-400">
                  {catalogQuery.error instanceof Error
                    ? catalogQuery.error.message
                    : "Could not load market catalog (is the Lab API running?)."}
                </p>
              )}
              {syncMarketsMutation.isError && (
                <p className="text-sm text-red-400">
                  {syncMarketsMutation.error instanceof Error
                    ? syncMarketsMutation.error.message
                    : "Market sync failed."}
                  {state.marketScope === "nobitex_all" && (
                    <span className="mt-1 block text-amber-200/90">
                      Nobitex may be blocked from your network (SSL/VPN). Use{" "}
                      <strong>Load offline catalog</strong> or switch scope to{" "}
                      <strong>Crypto 1h jobs file</strong>, then Sync.
                    </span>
                  )}
                </p>
              )}
              {catalogEmpty && !catalogQuery.isLoading && (
                <p className="text-sm text-amber-200/90">
                  Market catalog is empty. Click <strong>Sync catalog</strong> (needs network to Nobitex), or switch
                  scope to <strong>Crypto 1h jobs file</strong> for offline pairs.
                </p>
              )}
              {searchNeedle.length > 0 && marketsSearchQuery.isFetching && (
                <p className="text-sm text-muted">Searching…</p>
              )}

              {(totalInCatalog > 0 || displayMarkets.length > 0 || searchNeedle.length > 0) && (
                <>
                  <p className="text-xs text-muted">
                    {displayMarkets.length.toLocaleString()} shown
                    {searchNeedle
                      ? marketsSearchQuery.data?.matched_count != null
                        ? ` (matched ${marketsSearchQuery.data.matched_count.toLocaleString()})`
                        : ""
                      : totalInCatalog > 0
                        ? ` of ${totalInCatalog.toLocaleString()}`
                        : ""}
                    {catalogQuery.data?.updated_at_utc
                      ? ` · synced ${formatUtcTimestamp(catalogQuery.data.updated_at_utc)}`
                      : ""}
                  </p>
                  <div className="space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-sm text-slate-200">
                        Markets × horizons{" "}
                        <span className="text-xs text-muted">
                          ({state.exportMarketSymbols.length} markets × {state.exportIntervals.length || 1} horizons)
                        </span>
                      </span>
                      <div className="flex gap-2">
                        <Button
                          type="button"
                          variant="secondary"
                          onClick={() =>
                            onChange({
                              exportMarketSymbols: displayMarkets.slice(0, 24).map((market) => market.symbol),
                            })
                          }
                        >
                          Select filtered
                        </Button>
                        <Button
                          type="button"
                          variant="secondary"
                          disabled={state.exportMarketSymbols.length === 0 && state.exportIntervals.length === 0}
                          onClick={() =>
                            onChange({ exportMarketSymbols: [], exportIntervals: [], exportDaysByInterval: {}, exportStepsByInterval: {} })
                          }
                        >
                          Clear batch
                        </Button>
                      </div>
                    </div>
                    <p className="text-xs text-muted">
                      Tick horizons and markets to download every combination as part of the same
                      job (max 24 combos), then compare runs on all of them.
                    </p>
                    <Field label="Horizons">
                      <div className="flex flex-wrap gap-2">
                        {resolutions.map((resolution) => {
                          const checked = state.exportIntervals.includes(resolution);
                          return (
                            <label
                              key={resolution}
                              className={`flex cursor-pointer items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs ${
                                checked ? "border-accent bg-accent/10 text-white" : "border-border text-muted"
                              }`}
                            >
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() =>
                                  onChange({
                                    exportIntervals: checked
                                      ? state.exportIntervals.filter((item) => item !== resolution)
                                      : [...state.exportIntervals, resolution],
                                  })
                                }
                              />
                              {resolution}
                            </label>
                          );
                        })}
                      </div>
                      {state.exportIntervals.length > 0 && (
                        <div className="grid gap-2 sm:grid-cols-3">
                          {state.exportIntervals.map((interval) =>
                            state.exportHistoryMode === "steps" ? (
                              <Field key={interval} label={`${interval} steps (bars)`}>
                                <TextInput
                                  type="number"
                                  min={1}
                                  placeholder={state.exportSteps || "500"}
                                  value={state.exportStepsByInterval[interval] ?? ""}
                                  onChange={(event) =>
                                    onChange({
                                      exportStepsByInterval: {
                                        ...state.exportStepsByInterval,
                                        [interval]: event.target.value,
                                      },
                                    })
                                  }
                                />
                              </Field>
                            ) : (
                              <Field key={interval} label={`${interval} history (days)`}>
                                <TextInput
                                  type="number"
                                  min={1}
                                  placeholder={state.exportDays || "30"}
                                  value={state.exportDaysByInterval[interval] ?? ""}
                                  onChange={(event) =>
                                    onChange({
                                      exportDaysByInterval: {
                                        ...state.exportDaysByInterval,
                                        [interval]: event.target.value,
                                      },
                                    })
                                  }
                                />
                              </Field>
                            ),
                          )}
                        </div>
                      )}
                    </Field>
                    <div className="max-h-40 overflow-auto rounded-lg border border-border">
                      <table className="data">
                        <thead className="sticky top-0 bg-panel">
                          <tr>
                            <th />
                            <th>Pair</th>
                            <th>Symbol</th>
                          </tr>
                        </thead>
                        <tbody>
                          {displayMarkets.length === 0 && searchNeedle.length > 0 && !marketsSearchQuery.isFetching && (
                            <tr>
                              <td colSpan={3} className="px-3 py-4 text-sm text-muted">
                                No markets match &ldquo;{searchNeedle}&rdquo;. Try Sync catalog or another scope.
                              </td>
                            </tr>
                          )}
                          {displayMarkets.slice(0, 80).map((market) => {
                            const checked = state.exportMarketSymbols.includes(market.symbol);
                            return (
                              <tr key={market.symbol} className={checked ? "bg-accent/10" : undefined}>
                                <td>
                                  <input
                                    type="checkbox"
                                    checked={checked}
                                    onChange={() =>
                                      onChange({
                                        exportMarketSymbols: checked
                                          ? state.exportMarketSymbols.filter((item) => item !== market.symbol)
                                          : [...state.exportMarketSymbols, market.symbol],
                                      })
                                    }
                                    aria-label={`Batch ${market.symbol}`}
                                  />
                                </td>
                                <td>{market.label}</td>
                                <td className="font-mono text-xs">{market.symbol}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                    {state.exportMarketSymbols.length > 0 && (
                      <div className="rounded-lg border border-border bg-surface px-3 py-2">
                        <p className="text-xs text-muted">
                          Selected markets ({state.exportMarketSymbols.length})
                          {state.exportIntervals.length > 0
                            ? ` × horizons ${state.exportIntervals
                                .map((interval) => {
                                  if (state.exportHistoryMode === "steps") {
                                    const steps =
                                      state.exportStepsByInterval[interval] || state.exportSteps || "?";
                                    return `${interval} (${steps} bars)`;
                                  }
                                  return `${interval} (${state.exportDaysByInterval[interval] || state.exportDays || "30"}d)`;
                                })
                                .join(", ")}`
                            : ""}
                          :
                        </p>
                        <div className="mt-1.5 flex flex-wrap gap-1.5">
                          {state.exportMarketSymbols.map((symbol) => (
                            <button
                              key={symbol}
                              type="button"
                              title={`Remove ${symbol}`}
                              className="rounded-full border border-accent/40 bg-accent/10 px-2 py-0.5 font-mono text-xs text-slate-100 hover:border-red-400/60 hover:text-red-200"
                              onClick={() =>
                                onChange({
                                  exportMarketSymbols: state.exportMarketSymbols.filter(
                                    (item) => item !== symbol,
                                  ),
                                })
                              }
                            >
                              {symbol} ✕
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </>
              )}

              <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs text-muted">
                <p>
                  The custom pipeline exports the selected markets × horizons as part of the same job.
                  You can also{" "}
                  <button
                    type="button"
                    className="text-accent hover:underline"
                    disabled={
                      (state.exportMarketSymbols.length === 0 && !state.exportMarketSymbol.trim()) ||
                      standaloneExportMutation.isPending
                    }
                    onClick={() => standaloneExportMutation.mutate()}
                  >
                    {standaloneExportMutation.isPending ? "exporting…" : "run a standalone export"}
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
    if (state.exportMarketSymbols.length > 0) {
      return true;
    }
    return state.useAllHourly || state.datasetIds.length > 0;
  }
  return state.useAllHourly || state.datasetIds.length > 0;
}
