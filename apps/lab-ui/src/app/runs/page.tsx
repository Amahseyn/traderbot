"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { RunsTable } from "@/components/RunsTable";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import { Page } from "@/components/ui/Page";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { api } from "@/lib/api";
import { formatResolutionLabel } from "@/lib/format";
import { TablePagination } from "@/components/ui/TablePagination";

const RUNS_PAGE_SIZE = 25;

const RUN_HORIZON_FILTERS = [
  { value: "1m", label: "1 minute ahead" },
  { value: "5m", label: "5 minutes ahead" },
  { value: "15m", label: "15 minutes ahead" },
  { value: "30m", label: "30 minutes ahead" },
  { value: "1h", label: "1 hour ahead" },
  { value: "2h", label: "2 hours ahead" },
  { value: "3h", label: "3 hours ahead" },
  { value: "4h", label: "4 hours ahead" },
  { value: "6h", label: "6 hours ahead" },
  { value: "12h", label: "12 hours ahead" },
  { value: "1d", label: "1 day ahead" },
  { value: "2d", label: "2 days ahead" },
  { value: "3d", label: "3 days ahead" },
] as const;

const STANDARD_RESOLUTIONS = [
  { value: "1", label: "1m candles" },
  { value: "5", label: "5m candles" },
  { value: "15", label: "15m candles" },
  { value: "30", label: "30m candles" },
  { value: "60", label: "1h candles" },
  { value: "120", label: "2h candles" },
  { value: "240", label: "4h candles" },
  { value: "D", label: "1d candles" },
];

const OUTCOME_OPTIONS = [
  { value: "", label: "All outcomes" },
  { value: "profitable", label: "Profitable (> 0%)" },
  { value: "loss", label: "Unprofitable (< 0%)" },
  { value: "high_return", label: "High return (≥ +5%)" },
  { value: "breakeven", label: "Break-even (0%)" },
];

const SORT_OPTIONS = [
  { value: "created_at_desc", label: "Newest recorded" },
  { value: "created_at_asc", label: "Oldest recorded" },
  { value: "return_desc", label: "Highest return" },
  { value: "return_asc", label: "Lowest return" },
  { value: "win_rate_desc", label: "Highest win rate" },
  { value: "win_rate_asc", label: "Lowest win rate" },
  { value: "trades_desc", label: "Most trades" },
  { value: "trades_asc", label: "Fewest trades" },
  { value: "equity_desc", label: "Highest final equity" },
];

const OPTIMIZER_OPTIONS = [
  { value: "", label: "All parameters" },
  { value: "optimized", label: "Optimized / tuned only" },
  { value: "default", label: "Default parameters only" },
];

const TRADE_OPTIONS = [
  { value: "", label: "All activity" },
  { value: "with_trades", label: "With trades (> 0)" },
  { value: "no_trades", label: "Zero trades (0)" },
];

const DATE_RANGE_OPTIONS = [
  { value: "", label: "All time" },
  { value: "24h", label: "Last 24 hours" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
];

const RUN_KIND_OPTIONS = [
  { value: "", label: "All kinds" },
  { value: "strategy_backtest", label: "Strategy backtest" },
  { value: "model_forecast", label: "Model forecast" },
];

function RunsPageContent() {
  const searchParams = useSearchParams();

  const [queryInput, setQueryInput] = useState(() => searchParams.get("query") ?? "");
  const [query, setQuery] = useState(() => searchParams.get("query") ?? "");
  const [runKind, setRunKind] = useState(() => searchParams.get("run_kind") ?? "");
  const [symbol, setSymbol] = useState(() => searchParams.get("symbol") ?? "");
  const [strategyId, setStrategyId] = useState(() => searchParams.get("strategy_id") ?? "");
  const [resolution, setResolution] = useState(() => searchParams.get("resolution") ?? "");
  const [horizonLabel, setHorizonLabel] = useState(() => searchParams.get("horizon_label") ?? "");
  const [outcome, setOutcome] = useState(() => searchParams.get("outcome") ?? "");
  const [optimizer, setOptimizer] = useState(() => searchParams.get("optimizer") ?? "");
  const [trades, setTrades] = useState(() => searchParams.get("trades") ?? "");
  const [dateRange, setDateRange] = useState(() => searchParams.get("date_range") ?? "");
  const [sortBy, setSortBy] = useState(() => searchParams.get("sort_by") ?? "created_at_desc");

  const [showAdvanced, setShowAdvanced] = useState(() => {
    return Boolean(
      searchParams.get("run_kind") ||
      searchParams.get("horizon_label") ||
      searchParams.get("optimizer") ||
      searchParams.get("trades") ||
      searchParams.get("date_range")
    );
  });

  const [runsPage, setRunsPage] = useState(1);

  // Debounce search text input
  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(queryInput.trim());
    }, 300);
    return () => clearTimeout(timer);
  }, [queryInput]);

  // Combined filters object
  const filters = useMemo(
    () => ({
      query: query || undefined,
      run_kind: runKind || undefined,
      symbol: symbol || undefined,
      strategy_id: strategyId || undefined,
      resolution: resolution || undefined,
      horizon_label: horizonLabel || undefined,
      outcome: outcome || undefined,
      optimizer: optimizer || undefined,
      trades: trades || undefined,
      date_range: dateRange || undefined,
      sort_by: sortBy !== "created_at_desc" ? sortBy : undefined,
    }),
    [
      query,
      runKind,
      symbol,
      strategyId,
      resolution,
      horizonLabel,
      outcome,
      optimizer,
      trades,
      dateRange,
      sortBy,
    ],
  );

  // Reset pagination to page 1 whenever any filter changes
  useEffect(() => {
    setRunsPage(1);
  }, [filters]);

  // Synchronize active filters with the URL search query without reloading
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams();
    if (query) params.set("query", query);
    if (runKind) params.set("run_kind", runKind);
    if (symbol) params.set("symbol", symbol);
    if (strategyId) params.set("strategy_id", strategyId);
    if (resolution) params.set("resolution", resolution);
    if (horizonLabel) params.set("horizon_label", horizonLabel);
    if (outcome) params.set("outcome", outcome);
    if (optimizer) params.set("optimizer", optimizer);
    if (trades) params.set("trades", trades);
    if (dateRange) params.set("date_range", dateRange);
    if (sortBy && sortBy !== "created_at_desc") params.set("sort_by", sortBy);

    const queryString = params.toString();
    const newUrl = queryString ? `${window.location.pathname}?${queryString}` : window.location.pathname;
    window.history.replaceState(null, "", newUrl);
  }, [
    query,
    runKind,
    symbol,
    strategyId,
    resolution,
    horizonLabel,
    outcome,
    optimizer,
    trades,
    dateRange,
    sortBy,
  ]);

  // Fetch runs with server-side pagination and total count
  const offset = (runsPage - 1) * RUNS_PAGE_SIZE;
  const runsQuery = useQuery({
    queryKey: ["runs", filters, { limit: RUNS_PAGE_SIZE, offset }],
    queryFn: () =>
      api.runsPaginated({
        limit: RUNS_PAGE_SIZE,
        offset,
        ...filters,
      }),
    refetchInterval: 15_000,
    placeholderData: (prev) => prev,
  });

  const datasetsQuery = useQuery({ queryKey: ["datasets"], queryFn: () => api.datasets() });
  const strategiesQuery = useQuery({
    queryKey: ["catalog-strategies"],
    queryFn: () => api.catalogStrategies(false),
  });

  const rows = runsQuery.data?.data ?? [];
  const totalCount = runsQuery.data?.total ?? 0;

  const runsPageCount = useMemo(
    () => Math.max(1, Math.ceil(totalCount / RUNS_PAGE_SIZE)),
    [totalCount],
  );
  const runsPageClamped = Math.min(Math.max(runsPage, 1), runsPageCount);

  useEffect(() => {
    if (runsPage !== runsPageClamped) {
      setRunsPage(runsPageClamped);
    }
  }, [runsPage, runsPageClamped]);

  const symbols = useMemo(() => {
    const values = new Set<string>();
    for (const dataset of datasetsQuery.data ?? []) {
      if (dataset.symbol) values.add(dataset.symbol);
    }
    if (symbol) values.add(symbol);
    return [...values].sort();
  }, [datasetsQuery.data, symbol]);

  const resolutions = useMemo(() => {
    const map = new Map<string, string>();
    for (const standard of STANDARD_RESOLUTIONS) {
      map.set(standard.value, standard.label);
    }
    for (const dataset of datasetsQuery.data ?? []) {
      if (dataset.resolution && !map.has(dataset.resolution)) {
        map.set(dataset.resolution, formatResolutionLabel(dataset.resolution));
      }
    }
    if (resolution && !map.has(resolution)) {
      map.set(resolution, formatResolutionLabel(resolution));
    }
    return [...map.entries()].map(([val, lab]) => ({ value: val, label: lab }));
  }, [datasetsQuery.data, resolution]);

  const strategies = strategiesQuery.data ?? [];

  const advancedFiltersActiveCount = useMemo(() => {
    let count = 0;
    if (runKind) count++;
    if (horizonLabel) count++;
    if (optimizer) count++;
    if (trades) count++;
    if (dateRange) count++;
    return count;
  }, [runKind, horizonLabel, optimizer, trades, dateRange]);

  const activeFilters = useMemo(() => {
    const list: { key: string; label: string; onRemove: () => void }[] = [];
    if (query) {
      list.push({
        key: "query",
        label: `Search: "${query}"`,
        onRemove: () => {
          setQueryInput("");
          setQuery("");
        },
      });
    }
    if (symbol) {
      list.push({
        key: "symbol",
        label: `Symbol: ${symbol}`,
        onRemove: () => setSymbol(""),
      });
    }
    if (strategyId) {
      const match = strategies.find((s) => s.id === strategyId);
      list.push({
        key: "strategy",
        label: `Strategy: ${match?.name || strategyId}`,
        onRemove: () => setStrategyId(""),
      });
    }
    if (resolution) {
      const resMatch = resolutions.find((r) => r.value === resolution);
      list.push({
        key: "resolution",
        label: `Interval: ${resMatch?.label || resolution}`,
        onRemove: () => setResolution(""),
      });
    }
    if (outcome) {
      const outMatch = OUTCOME_OPTIONS.find((o) => o.value === outcome);
      list.push({
        key: "outcome",
        label: `Outcome: ${outMatch?.label || outcome}`,
        onRemove: () => setOutcome(""),
      });
    }
    if (sortBy && sortBy !== "created_at_desc") {
      const sortMatch = SORT_OPTIONS.find((s) => s.value === sortBy);
      list.push({
        key: "sort",
        label: `Sort: ${sortMatch?.label || sortBy}`,
        onRemove: () => setSortBy("created_at_desc"),
      });
    }
    if (runKind) {
      const kindMatch = RUN_KIND_OPTIONS.find((k) => k.value === runKind);
      list.push({
        key: "kind",
        label: `Kind: ${kindMatch?.label || runKind}`,
        onRemove: () => setRunKind(""),
      });
    }
    if (horizonLabel) {
      const horMatch = RUN_HORIZON_FILTERS.find((h) => h.value === horizonLabel);
      list.push({
        key: "horizon",
        label: `Horizon: ${horMatch?.label || horizonLabel}`,
        onRemove: () => setHorizonLabel(""),
      });
    }
    if (optimizer) {
      const optMatch = OPTIMIZER_OPTIONS.find((o) => o.value === optimizer);
      list.push({
        key: "optimizer",
        label: `Optimizer: ${optMatch?.label || optimizer}`,
        onRemove: () => setOptimizer(""),
      });
    }
    if (trades) {
      const trMatch = TRADE_OPTIONS.find((t) => t.value === trades);
      list.push({
        key: "trades",
        label: `Trades: ${trMatch?.label || trades}`,
        onRemove: () => setTrades(""),
      });
    }
    if (dateRange) {
      const drMatch = DATE_RANGE_OPTIONS.find((d) => d.value === dateRange);
      list.push({
        key: "dateRange",
        label: `Window: ${drMatch?.label || dateRange}`,
        onRemove: () => setDateRange(""),
      });
    }
    return list;
  }, [
    query,
    symbol,
    strategyId,
    strategies,
    resolution,
    resolutions,
    outcome,
    sortBy,
    runKind,
    horizonLabel,
    optimizer,
    trades,
    dateRange,
  ]);

  const hasFilters = activeFilters.length > 0;

  const clearFilters = () => {
    setQueryInput("");
    setQuery("");
    setRunKind("");
    setSymbol("");
    setStrategyId("");
    setResolution("");
    setHorizonLabel("");
    setOutcome("");
    setOptimizer("");
    setTrades("");
    setDateRange("");
    setSortBy("created_at_desc");
  };

  return (
    <Page>
      <PageHeader
        eyebrow="Run Archive"
        title="Runs"
        description="Strategy backtests in the catalog. Filter by pair, algorithm, candle resolution, outcome, optimizer status, or date range, then click a run to view trade logs and curves."
        actions={
          <Button
            variant="secondary"
            onClick={() => void runsQuery.refetch()}
            disabled={runsQuery.isFetching}
          >
            {runsQuery.isFetching ? "Refreshing…" : "Refresh"}
          </Button>
        }
      />

      <div className="panel-inset space-y-3 text-sm">
        {/* Search Bar + Controls */}
        <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative flex-1">
            <TextInput
              placeholder="Filter by ID, symbol, strategy name, dataset path…"
              value={queryInput}
              onChange={(event) => setQueryInput(event.target.value)}
              className="pr-8"
            />
            {queryInput && (
              <button
                type="button"
                onClick={() => {
                  setQueryInput("");
                  setQuery("");
                }}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 text-muted hover:text-white transition-colors duration-150 focus:outline-none"
                title="Clear search input"
              >
                <span aria-hidden="true" className="font-mono text-xs">✕</span>
                <span className="sr-only">Clear search</span>
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              onClick={() => setShowAdvanced((prev) => !prev)}
              className="whitespace-nowrap"
            >
              <span>{showAdvanced ? "Fewer filters" : "More filters"}</span>
              {advancedFiltersActiveCount > 0 && (
                <span className="rounded-full bg-accent/20 px-1.5 py-0.2 text-[10px] font-semibold text-accent">
                  +{advancedFiltersActiveCount}
                </span>
              )}
            </Button>
            {hasFilters && (
              <Button
                variant="ghost"
                onClick={clearFilters}
                className="text-muted hover:text-white"
              >
                Reset all
              </Button>
            )}
          </div>
        </div>

        {/* Primary Filter Grid */}
        <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5">
          <Field label="Symbol">
            <SelectInput value={symbol} onChange={(event) => setSymbol(event.target.value)}>
              <option value="">All symbols</option>
              {symbols.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </SelectInput>
          </Field>
          <Field label="Strategy">
            <SelectInput value={strategyId} onChange={(event) => setStrategyId(event.target.value)}>
              <option value="">All strategies</option>
              {strategyId && !strategies.some((strategy) => strategy.id === strategyId) && (
                <option value={strategyId}>{strategyId}</option>
              )}
              {strategies.map((strategy) => (
                <option key={strategy.id} value={strategy.id}>
                  {strategy.name || strategy.id}
                </option>
              ))}
            </SelectInput>
          </Field>
          <Field label="Interval">
            <SelectInput value={resolution} onChange={(event) => setResolution(event.target.value)}>
              <option value="">All intervals</option>
              {resolutions.map((res) => (
                <option key={res.value} value={res.value}>
                  {res.label}
                </option>
              ))}
            </SelectInput>
          </Field>
          <Field label="Outcome">
            <SelectInput value={outcome} onChange={(event) => setOutcome(event.target.value)}>
              {OUTCOME_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </SelectInput>
          </Field>
          <Field label="Sort By">
            <SelectInput value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
              {SORT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </SelectInput>
          </Field>
        </div>

        {/* Secondary / Advanced Filters Grid (Collapsible) */}
        {showAdvanced && (
          <div className="grid gap-3 border-t border-border/60 pt-3 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 animate-in fade-in duration-150">
            <Field label="Kind">
              <SelectInput value={runKind} onChange={(event) => setRunKind(event.target.value)}>
                {RUN_KIND_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </SelectInput>
            </Field>
            <Field label="Horizon">
              <SelectInput value={horizonLabel} onChange={(event) => setHorizonLabel(event.target.value)}>
                <option value="">All horizons</option>
                {RUN_HORIZON_FILTERS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </SelectInput>
            </Field>
            <Field label="Optimizer">
              <SelectInput value={optimizer} onChange={(event) => setOptimizer(event.target.value)}>
                {OPTIMIZER_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </SelectInput>
            </Field>
            <Field label="Trade Activity">
              <SelectInput value={trades} onChange={(event) => setTrades(event.target.value)}>
                {TRADE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </SelectInput>
            </Field>
            <Field label="Time Window">
              <SelectInput value={dateRange} onChange={(event) => setDateRange(event.target.value)}>
                {DATE_RANGE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </SelectInput>
            </Field>
          </div>
        )}

        {/* Active Filter Chips */}
        {activeFilters.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 border-t border-border/40 pt-2.5">
            <span className="text-xs font-medium text-muted">
              Active filters ({activeFilters.length}):
            </span>
            {activeFilters.map((af) => (
              <span
                key={af.key}
                className="inline-flex items-center gap-1.5 rounded border border-border bg-panel-elevated px-2 py-0.5 text-xs text-slate-200"
              >
                <span>{af.label}</span>
                <button
                  type="button"
                  onClick={af.onRemove}
                  className="text-muted hover:text-white transition-colors duration-150 focus:outline-none"
                  title={`Remove ${af.label}`}
                >
                  <span aria-hidden="true" className="font-mono text-xs">✕</span>
                  <span className="sr-only">Remove {af.label}</span>
                </button>
              </span>
            ))}
            <button
              type="button"
              onClick={clearFilters}
              className="ml-auto text-xs font-medium text-accent hover:underline focus:outline-none"
            >
              Clear all
            </button>
          </div>
        )}
      </div>

      {(datasetsQuery.isError || strategiesQuery.isError) && (
        <ErrorState
          title="Filter catalogs unavailable"
          error={datasetsQuery.error ?? strategiesQuery.error}
          hintAuth={false}
        />
      )}

      {runsQuery.isLoading && <TableSkeleton rows={8} />}
      {runsQuery.isError && (
        <ErrorState
          title="Failed to load runs"
          error={runsQuery.error}
          action={<Button variant="secondary" onClick={() => runsQuery.refetch()}>Retry</Button>}
        />
      )}

      {runsQuery.isSuccess && rows.length === 0 && (
        <EmptyState
          title={hasFilters ? "No runs match these filters" : "No runs yet"}
          description={
            hasFilters ? (
              <>Try clearing one or more filters or search terms to broaden the catalog view.</>
            ) : (
              <>
                Export data under{" "}
                <Link href="/data" className="text-accent hover:underline">Data</Link> or start a job from{" "}
                <Link href="/custom" className="text-accent hover:underline">Custom research</Link>.
              </>
            )
          }
          action={
            hasFilters ? (
              <Button variant="secondary" onClick={clearFilters}>Clear filters</Button>
            ) : undefined
          }
        />
      )}

      {totalCount > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs text-muted">
            <p>Click a timestamp or ID to open details. Column headers can be clicked to sort.</p>
            <p className="tabular-nums font-mono">
              Showing {rows.length} of {totalCount} {totalCount === 1 ? "run" : "runs"}
            </p>
          </div>
          <RunsTable
            runs={rows}
            variant="full"
            sortBy={sortBy}
            onSort={(next) => setSortBy(next)}
          />
          <TablePagination
            page={runsPageClamped}
            pageCount={runsPageCount}
            pageSize={RUNS_PAGE_SIZE}
            totalCount={totalCount}
            itemLabel={totalCount === 1 ? "run" : "runs"}
            onPageChange={setRunsPage}
          />
        </div>
      )}
    </Page>
  );
}

export default function RunsPage() {
  return (
    <Suspense fallback={<TableSkeleton rows={8} />}>
      <RunsPageContent />
    </Suspense>
  );
}
