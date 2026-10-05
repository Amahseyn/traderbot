"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { JobMonitor } from "@/components/JobMonitor";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import Link from "next/link";
import { api, datasetDownloadUrl } from "@/lib/api";
import { formatUtcTimestamp } from "@/lib/format";

type MarketScope = "default_jobs" | "nobitex_all";

function marketMatchesSearch(
  market: { symbol: string; label: string; src: string; dst: string },
  needle: string,
): boolean {
  if (!needle) {
    return true;
  }
  return (
    market.symbol.toLowerCase().includes(needle) ||
    market.label.toLowerCase().includes(needle) ||
    market.src.toLowerCase().includes(needle) ||
    market.dst.toLowerCase().includes(needle)
  );
}

export default function DataPage() {
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const [marketScope, setMarketScope] = useState<MarketScope>("nobitex_all");
  const [marketSearch, setMarketSearch] = useState("");
  const [selectedSymbol, setSelectedSymbol] = useState("");

  const [exportInterval, setExportInterval] = useState("60");
  const [exportDays, setExportDays] = useState("30");

  const catalogQuery = useQuery({
    queryKey: ["data-markets-catalog", marketScope],
    queryFn: () => api.dataMarketsCatalog(marketScope),
    staleTime: 60_000,
  });

  const datasetsQuery = useQuery({
    queryKey: ["datasets"],
    queryFn: () => api.datasets(),
  });

  const syncMarketsMutation = useMutation({
    mutationFn: () => api.syncMarkets(marketScope),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["data-markets-catalog"] });
    },
  });

  const searchNeedle = marketSearch.trim().toLowerCase();
  const allMarkets = catalogQuery.data?.markets ?? [];
  const filteredMarkets = useMemo(
    () => allMarkets.filter((market) => marketMatchesSearch(market, searchNeedle)),
    [allMarkets, searchNeedle],
  );

  const resolutions = catalogQuery.data?.udf_resolutions ?? ["1", "15", "60", "D"];
  const totalInCatalog = catalogQuery.data?.total_in_catalog ?? 0;
  const catalogEmpty = !catalogQuery.isLoading && totalInCatalog === 0;

  const exportMutation = useMutation({
    mutationFn: () =>
      api.postJob("export", {
        market_symbol: selectedSymbol,
        interval: exportInterval,
        days: Number(exportDays),
        out: "data",
      }),
    onSuccess: (data) => setJobId(data.id),
  });

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="1 · Data"
        title="Data"
        description="Sync the Nobitex market catalog, export OHLC into data/, and download registered datasets for workbench jobs."
        actions={
          <Link href="/actions">
            <Button variant="secondary">Open workbench</Button>
          </Link>
        }
      />

      <div className="grid gap-8 lg:grid-cols-5">
        <div className="space-y-6 lg:col-span-3">
          <Card
            title="Nobitex markets"
            description="Cloned catalog in traderbot.db. Sync once (or after Nobitex updates), then search offline."
          >
            <div className="mb-4 flex flex-wrap items-end gap-3">
              <Field label="Catalog scope">
                <SelectInput
                  value={marketScope}
                  onChange={(event) => {
                    setMarketScope(event.target.value as MarketScope);
                    setSelectedSymbol("");
                    setMarketSearch("");
                  }}
                >
                  <option value="nobitex_all">All Nobitex (cloned)</option>
                  <option value="default_jobs">Crypto 1h jobs file</option>
                </SelectInput>
              </Field>
              <Field label="Search" hint="Filters the loaded catalog locally">
                <TextInput
                  placeholder="e.g. btc, eth/usdt, BTCIRT…"
                  value={marketSearch}
                  onChange={(event) => setMarketSearch(event.target.value)}
                  autoComplete="off"
                  disabled={catalogEmpty}
                />
              </Field>
              <Button
                type="button"
                variant="secondary"
                disabled={syncMarketsMutation.isPending}
                onClick={() => syncMarketsMutation.mutate()}
              >
                {syncMarketsMutation.isPending ? "Syncing…" : "Sync from Nobitex"}
              </Button>
            </div>

            {catalogQuery.isLoading && <p className="text-sm text-muted">Loading catalog from database…</p>}
            {catalogQuery.isError && (
              <p className="text-sm text-red-400">
                {catalogQuery.error instanceof Error
                  ? catalogQuery.error.message
                  : "Could not read market catalog from the database."}{" "}
                Run <code className="text-slate-200">./run-lab.sh</code> to restart the Lab API.
              </p>
            )}

            {syncMarketsMutation.isError && (
              <p className="text-sm text-red-400">
                {syncMarketsMutation.error instanceof Error
                  ? syncMarketsMutation.error.message
                  : "Sync failed."}
              </p>
            )}

            {!catalogQuery.isLoading && !catalogQuery.isError && catalogEmpty && (
              <p className="text-sm text-muted">
                No markets in this scope yet. Click <strong className="text-slate-200">Sync from Nobitex</strong>{" "}
                (or switch to Crypto 1h jobs file for the local jobs file).
              </p>
            )}

            {catalogQuery.data && totalInCatalog > 0 && (
              <>
                <p className="mb-2 text-xs text-muted">
                  {filteredMarkets.length.toLocaleString()} shown
                  {searchNeedle
                    ? ` (of ${totalInCatalog.toLocaleString()} in catalog)`
                    : ` · ${totalInCatalog.toLocaleString()} in catalog`}
                  {catalogQuery.data.updated_at_utc
                    ? ` · synced ${formatUtcTimestamp(catalogQuery.data.updated_at_utc)}`
                    : ""}
                </p>
                <div className="max-h-96 overflow-auto rounded-lg border border-border">
                  <table className="data">
                    <thead className="sticky top-0 bg-panel">
                      <tr>
                        <th>Pair</th>
                        <th>Symbol</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {filteredMarkets.map((market) => {
                        const selected = market.symbol === selectedSymbol;
                        return (
                          <tr key={market.symbol} className={selected ? "bg-accent/10" : undefined}>
                            <td>{market.label}</td>
                            <td className="font-mono text-xs">{market.symbol}</td>
                            <td>
                              <button
                                type="button"
                                className="text-xs text-accent hover:underline"
                                onClick={() => setSelectedSymbol(market.symbol)}
                              >
                                Use for export
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                {filteredMarkets.length === 0 && searchNeedle && (
                  <p className="mt-2 text-sm text-muted">No markets match “{marketSearch.trim()}”.</p>
                )}
              </>
            )}
          </Card>

          <Card title="Export OHLC" description="Runs traderbot export; new CSVs are registered as catalog datasets.">
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                exportMutation.mutate();
              }}
            >
              <Field label="Market">
                <SelectInput value={selectedSymbol} onChange={(e) => setSelectedSymbol(e.target.value)}>
                  <option value="">Select market…</option>
                  {selectedSymbol &&
                    !filteredMarkets.some((market) => market.symbol === selectedSymbol) && (
                      <option value={selectedSymbol}>{selectedSymbol}</option>
                    )}
                  {filteredMarkets.slice(0, 200).map((market) => (
                    <option key={market.symbol} value={market.symbol}>
                      {market.label} ({market.symbol})
                    </option>
                  ))}
                </SelectInput>
              </Field>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Interval">
                  <SelectInput
                    value={exportInterval}
                    onChange={(e) => setExportInterval(e.target.value)}
                  >
                    {resolutions.map((resolution) => (
                      <option key={resolution} value={resolution}>
                        {resolution}
                      </option>
                    ))}
                  </SelectInput>
                </Field>
                <Field label="History (days)">
                  <TextInput
                    type="number"
                    min={1}
                    value={exportDays}
                    onChange={(e) => setExportDays(e.target.value)}
                  />
                </Field>
              </div>
              {exportMutation.isError && (
                <p className="text-sm text-red-400">
                  {exportMutation.error instanceof Error
                    ? exportMutation.error.message
                    : "Export job failed to start."}
                </p>
              )}
              <Button type="submit" disabled={exportMutation.isPending || !selectedSymbol}>
                {exportMutation.isPending ? "Starting export…" : "Start export job"}
              </Button>
            </form>
          </Card>

          <Card title="Catalog datasets" description="Registered OHLC CSVs (from exports, backtests, and compares).">
            {datasetsQuery.isLoading && <p className="text-sm text-muted">Loading datasets…</p>}
            {!datasetsQuery.isLoading && (datasetsQuery.data ?? []).length === 0 && (
              <p className="text-sm text-muted">No datasets in the catalog yet.</p>
            )}
            {(datasetsQuery.data ?? []).length > 0 && (
              <table className="data">
                <thead>
                  <tr>
                    <th>Price file</th>
                    <th>Horizon</th>
                    <th>Start</th>
                    <th>End</th>
                    <th>Source</th>
                    <th>Updated</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {(datasetsQuery.data ?? []).map((dataset) => (
                    <tr key={dataset.id}>
                      <td>{dataset.label}</td>
                      <td className="text-xs text-muted">{dataset.horizon_label ?? "—"}</td>
                      <td className="text-xs text-muted">{dataset.range_start_utc ?? "—"}</td>
                      <td className="text-xs text-muted">{dataset.range_end_utc ?? "—"}</td>
                      <td className="text-xs text-muted">{dataset.source}</td>
                      <td className="text-xs text-muted">
                        {formatUtcTimestamp(dataset.last_seen_at_utc)}
                      </td>
                      <td>
                        <a
                          href={datasetDownloadUrl(dataset.id)}
                          className="text-xs text-accent hover:underline"
                        >
                          Download
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </div>

        <div className="lg:col-span-2">
          <JobMonitor activeJobId={jobId} onSelectJob={setJobId} />
        </div>
      </div>
    </div>
  );
}
