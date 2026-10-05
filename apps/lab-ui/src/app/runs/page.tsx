"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { RunsTable } from "@/components/RunsTable";
import { Field, SelectInput } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { api } from "@/lib/api";
import { HORIZON_OPTIONS } from "@/lib/pipelines";

function RunsPageContent() {
  const searchParams = useSearchParams();
  const [runKind, setRunKind] = useState(() => searchParams.get("run_kind") ?? "");
  const [symbol, setSymbol] = useState(() => searchParams.get("symbol") ?? "");
  const [strategyId, setStrategyId] = useState(() => searchParams.get("strategy_id") ?? "");
  const [horizonLabel, setHorizonLabel] = useState(() => searchParams.get("horizon_label") ?? "");

  const queryString = useMemo(() => {
    const params = new URLSearchParams();
    if (runKind) params.set("run_kind", runKind);
    if (symbol) params.set("symbol", symbol);
    if (strategyId) params.set("strategy_id", strategyId);
    if (horizonLabel) params.set("horizon_label", horizonLabel);
    const serialized = params.toString();
    return serialized ? `?${serialized}` : "";
  }, [runKind, symbol, strategyId, horizonLabel]);

  const runsQuery = useQuery({
    queryKey: ["runs", queryString],
    queryFn: () => api.runs(queryString),
  });
  const datasetsQuery = useQuery({ queryKey: ["datasets"], queryFn: () => api.datasets() });
  const strategiesQuery = useQuery({
    queryKey: ["catalog-strategies"],
    queryFn: () => api.catalogStrategies(false),
  });

  const rows = runsQuery.data ?? [];
  const symbols = useMemo(() => {
    const values = new Set<string>();
    for (const dataset of datasetsQuery.data ?? []) {
      if (dataset.symbol) values.add(dataset.symbol);
    }
    if (symbol) values.add(symbol);
    return [...values].sort();
  }, [datasetsQuery.data, symbol]);
  const strategies = strategiesQuery.data ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Review"
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
            {HORIZON_OPTIONS.filter((option) => option.value !== "usual" && option.value !== "all").map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </SelectInput>
        </Field>
      </div>

      {runsQuery.isLoading && <p className="text-muted">Loading runs…</p>}
      {runsQuery.isError && <p className="text-red-400">Failed to load runs.</p>}

      {!runsQuery.isLoading && rows.length === 0 && (
        <p className="text-muted text-sm">
          No runs match these filters. Export data under{" "}
          <Link href="/data" className="text-accent hover:underline">
            Data
          </Link>{" "}
          or start a job from{" "}
          <Link href="/custom" className="text-accent hover:underline">
            Custom research
          </Link>
          .
        </p>
      )}

      {rows.length > 0 && (
        <p className="text-muted text-xs">
          {rows.length} run{rows.length === 1 ? "" : "s"} — click a timestamp or ID to open details.
        </p>
      )}

      {rows.length > 0 && <RunsTable runs={rows} variant="full" />}
    </div>
  );
}

export default function RunsPage() {
  return (
    <Suspense fallback={<p className="text-muted">Loading runs…</p>}>
      <RunsPageContent />
    </Suspense>
  );
}
