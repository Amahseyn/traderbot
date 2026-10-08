"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import { api, type MarketSpec } from "@/lib/api";
import { formatUtcTimestamp } from "@/lib/format";
import { marketMatchesSearch, type MarketScope } from "@/lib/dataFilters";

type MarketSearchPickerProps = {
  selectedSymbol: string | null;
  onSelect: (market: MarketSpec) => void;
  /** Checkbox column — tick markets to include in a batch run. */
  batchMode?: boolean;
  batchSymbols?: string[];
  onToggleBatch?: (market: MarketSpec) => void;
  onClearBatch?: () => void;
  maxBatchSelect?: number;
};

export function MarketSearchPicker({
  selectedSymbol,
  onSelect,
  batchMode = false,
  batchSymbols = [],
  onToggleBatch,
  onClearBatch,
  maxBatchSelect = 16,
}: MarketSearchPickerProps) {
  const queryClient = useQueryClient();
  const [marketScope, setMarketScope] = useState<MarketScope>("nobitex_all");
  const [marketSearch, setMarketSearch] = useState("");

  const catalogQuery = useQuery({
    queryKey: ["data-markets-catalog", marketScope],
    queryFn: () => api.dataMarketsCatalog(marketScope),
    staleTime: 60_000,
  });

  const searchNeedle = marketSearch.trim();
  const marketsSearchQuery = useQuery({
    queryKey: ["data-markets-search", marketScope, searchNeedle],
    queryFn: () =>
      api.dataMarkets({
        scope: marketScope,
        q: searchNeedle || undefined,
        limit: 200,
      }),
    enabled: searchNeedle.length > 0,
    staleTime: 30_000,
  });

  const syncMarketsMutation = useMutation({
    mutationFn: (scope?: MarketScope) => api.syncMarkets(scope ?? marketScope),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["data-markets-catalog"] });
      queryClient.invalidateQueries({ queryKey: ["data-markets-search"] });
    },
  });

  const catalogMarkets = catalogQuery.data?.markets ?? [];
  const displayMarkets = useMemo(() => {
    if (searchNeedle.length > 0) {
      return marketsSearchQuery.data?.markets ?? [];
    }
    return catalogMarkets.filter((market) => marketMatchesSearch(market, searchNeedle)).slice(0, 200);
  }, [catalogMarkets, marketsSearchQuery.data?.markets, searchNeedle]);

  const totalInCatalog = catalogQuery.data?.total_in_catalog ?? catalogMarkets.length;
  const selectedMarket =
    catalogMarkets.find((market) => market.symbol === selectedSymbol) ??
    displayMarkets.find((market) => market.symbol === selectedSymbol);

  const batchAtCap = batchSymbols.length >= maxBatchSelect;

  function selectFilteredForBatch() {
    if (!onToggleBatch) {
      return;
    }
    const remaining = maxBatchSelect - batchSymbols.length;
    if (remaining <= 0) {
      return;
    }
    const toAdd = displayMarkets
      .filter((market) => !batchSymbols.includes(market.symbol))
      .slice(0, remaining);
    for (const market of toAdd) {
      onToggleBatch(market);
    }
  }

  return (
    <div className="space-y-3">
      {selectedMarket && (
        <p className="text-sm text-slate-200">
          Active for parameters:{" "}
          <span className="font-medium text-white">{selectedMarket.label}</span>{" "}
          <span className="font-mono text-xs text-muted">({selectedMarket.symbol})</span>
        </p>
      )}

      {batchMode && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-surface/60 px-3 py-2">
          <p className="text-xs text-muted">
            <span className="font-medium text-slate-200">{batchSymbols.length}</span> market
            {batchSymbols.length === 1 ? "" : "s"} in batch
            {batchAtCap ? ` (max ${maxBatchSelect})` : ""}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="secondary"
              className="text-xs"
              disabled={displayMarkets.length === 0 || batchAtCap}
              onClick={() => selectFilteredForBatch()}
            >
              Select shown
            </Button>
            <Button
              type="button"
              variant="secondary"
              className="text-xs"
              disabled={batchSymbols.length === 0}
              onClick={() => onClearBatch?.()}
            >
              Clear batch
            </Button>
          </div>
        </div>
      )}

      {batchMode && batchSymbols.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {batchSymbols.map((symbol) => (
            <span
              key={symbol}
              className="rounded-full border border-accent/40 bg-accent/10 px-2 py-0.5 font-mono text-xs text-slate-100"
            >
              {symbol}
            </span>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-end gap-3">
        <Field label="Catalog scope">
          <SelectInput
            value={marketScope}
            onChange={(event) => {
              setMarketScope(event.target.value as MarketScope);
              setMarketSearch("");
            }}
          >
            <option value="nobitex_all">All Nobitex (cloned)</option>
            <option value="default_jobs">Crypto 1h jobs file</option>
          </SelectInput>
        </Field>
        <Field label="Search markets" hint="btc, eth/usdt…">
          <TextInput
            placeholder="Search…"
            value={marketSearch}
            onChange={(event) => setMarketSearch(event.target.value)}
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
      {syncMarketsMutation.isError && (
        <p className="text-sm text-red-400">
          {syncMarketsMutation.error instanceof Error
            ? syncMarketsMutation.error.message
            : "Market sync failed."}
        </p>
      )}

      <p className="text-xs text-muted">
        {batchMode
          ? "Check markets to include in the batch. Click a row to set which pair strategy parameters apply to."
          : "Click a row to select the trading pair."}
      </p>

      <p className="text-xs text-muted">
        {displayMarkets.length.toLocaleString()} shown
        {searchNeedle && marketsSearchQuery.data?.matched_count != null
          ? ` (matched ${marketsSearchQuery.data.matched_count.toLocaleString()})`
          : totalInCatalog > 0
            ? ` of ${totalInCatalog.toLocaleString()}`
            : ""}
        {catalogQuery.data?.updated_at_utc
          ? ` · synced ${formatUtcTimestamp(catalogQuery.data.updated_at_utc)}`
          : ""}
      </p>

      <div className="max-h-56 overflow-y-auto rounded-lg border border-border">
        <table className="data">
          <thead className="sticky top-0 bg-panel">
            <tr>
              {batchMode && <th className="w-10" />}
              <th>Market</th>
              <th>Symbol</th>
            </tr>
          </thead>
          <tbody>
            {displayMarkets.map((market) => {
              const active = selectedSymbol === market.symbol;
              const inBatch = batchSymbols.includes(market.symbol);
              return (
                <tr
                  key={market.symbol}
                  className={`cursor-pointer ${
                    active ? "bg-accent/15" : inBatch ? "bg-accent/5" : "hover:bg-surface"
                  }`}
                  onClick={() => onSelect(market)}
                >
                  {batchMode && (
                    <td onClick={(event) => event.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={inBatch}
                        disabled={!inBatch && batchAtCap}
                        onChange={() => onToggleBatch?.(market)}
                        aria-label={`Include ${market.symbol} in batch`}
                      />
                    </td>
                  )}
                  <td className="text-sm">{market.label}</td>
                  <td className="font-mono text-xs text-muted">{market.symbol}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {displayMarkets.length === 0 && !catalogQuery.isLoading && (
          <p className="p-3 text-sm text-muted">No markets match. Sync the catalog or change the search.</p>
        )}
      </div>
    </div>
  );
}
