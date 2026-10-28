"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { RunsTable } from "@/components/RunsTable";
import { Field, SelectInput } from "@/components/ui/Field";
import { Page } from "@/components/ui/Page";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { api } from "@/lib/api";
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
  { value: "12h", label: "12 minutes ahead" },
  { value: "1d", label: "1 day ahead" },
  { value: "2d", label: "2 days ahead" },
  { value: "3d", label: "3 days ahead" },
] as const;

function RunsPageContent() {
  const searchParams = useSearchParams();
  const [runKind, setRunKind] = useState(() => searchParams.get("run_kind") ?? "");
  const [symbol, setSymbol] = useState(() => searchParams.get("symbol") ?? "");
  const [strategyId, setStrategyId] = useState(() => searchParams.get("strategy_id") ?? "");
  const [horizonLabel, setHorizonLabel] = useState(() => searchParams.get("horizon_label") ?? "");
  const [runsPage, setRunsPage] = useState(1);

  // Filters object — changes whenever any filter changes.
  const filters = useMemo(
    () => ({
      run_kind: runKind || undefined,
      symbol: symbol || undefined,
      strategy_id: strategyId || undefined,
      horizon_label: horizonLabel || undefined,
    }),
    [runKind, symbol, strategyId, horizonLabel],
  );

  // Reset to page 1 whenever the filters change.
  useEffect(() => {
    setRunsPage(1);
  }, [runKind, symbol, strategyId, horizonLabel]);

  // Server-driven pagination: fetch one page at a time.
  const offset = (runsPage - 1) * RUNS_PAGE_SIZE;
  const runsQuery = useQuery({
    queryKey: ["runs", filters, { limit: RUNS_PAGE_SIZE, offset }],
    queryFn: () =>
      api.runsPaginated({
        limit: RUNS_PAGE_SIZE,
        offset,
        ...filters,
      }),
    placeholderData: (prev) => prev, // keep previous page visible while loading the next
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
  const strategies = strategiesQuery.data ?? [];
  const hasFilters = Boolean(runKind || symbol || strategyId || horizonLabel);
  const clearFilters = () => {
    setRunKind("");
    setSymbol("");
    setStrategyId("");
    setHorizonLabel("");
  };

  return (
    <Page>
      <PageHeader
        eyebrow="Run Archive"
        title="Runs"
        description="Strategy backtests in the catalog. Filter the list, then open a run for trade logs, charts, and parameters."
      />

      <div className="panel-inset grid gap-3 sm:grid-cols-2 lg:grid-cols-4 text-sm">
        <Field label="Kind">
          <SelectInput value={runKind} onChange={(event) => setRunKind(event.target.value)}>
            <option value="">All</option>
            <option value="strategy_backtest">Strategy backtest</option>
          </SelectInput>
        </Field>
        <Field label="Symbol">
          <SelectInput value={symbol} onChange={(event) => setSymbol(event.target.value)}>
            <option value="">All</option>
            {symbols.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </SelectInput>
        </Field>
        <Field label="Strategy">
          <SelectInput value={strategyId} onChange={(event) => setStrategyId(event.target.value)}>
            <option value="">All</option>
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
        <Field label="Horizon">
          <SelectInput value={horizonLabel} onChange={(event) => setHorizonLabel(event.target.value)}>
            <option value="">All</option>
            {RUN_HORIZON_FILTERS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </SelectInput>
        </Field>
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
            <>
              Export data under{" "}
              <Link href="/data" className="text-accent hover:underline">Data</Link> or start a job from{" "}
              <Link href="/custom" className="text-accent hover:underline">Custom research</Link>.
            </>
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
          <p className="text-muted text-xs">Click a timestamp or ID to open details.</p>
          <RunsTable runs={rows} variant="full" />
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
