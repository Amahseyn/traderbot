"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import { PageHeader } from "@/components/ui/PageHeader";
import { SelectInput } from "@/components/ui/Field";
import { api, type ConfigurationRow } from "@/lib/api";
import { formatUtcTimestamp } from "@/lib/format";

function configKindBadgeClass(kind: string): string {
  if (kind === "strategy") return "badge badge-strategy";
  if (kind === "model") return "badge badge-model";
  return "badge";
}

const FIELD_LABELS: Record<string, string> = {
  model_id: "Model",
  horizon: "Horizon",
  horizon_label: "Horizon",
  horizon_bars: "Bars ahead",
  bar_minutes: "Candle minutes",
  run_lightgbm: "Run LightGBM",
  all_assets: "Every file",
  symbol: "Symbol",
  window_hours: "Holdout window",
  train_supervised_row_count: "Training rows",
  num_boost_round: "Boosting rounds",
  initial_cash: "Starting cash",
  train_ratio: "Training share",
  strategy_id: "Strategy",
  resolution: "Candle size",
  dataset: "Price file",
};

function formatFieldValue(value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (Array.isArray(value)) return value.map((item) => formatFieldValue(item)).join(", ");
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => `${FIELD_LABELS[key] ?? key.replaceAll("_", " ")}: ${formatFieldValue(item)}`)
      .join(" · ");
  }
  return String(value);
}

function RecordFields({ value }: { value: Record<string, unknown> }) {
  const entries = Object.entries(value);
  if (entries.length === 0) return <p className="text-sm text-muted">None stored.</p>;
  return (
    <dl className="grid gap-3 sm:grid-cols-2">
      {entries.map(([key, item]) => (
        <div key={key}>
          <dt className="text-xs text-muted">{FIELD_LABELS[key] ?? key.replaceAll("_", " ")}</dt>
          <dd className="text-sm text-slate-100">{formatFieldValue(item)}</dd>
        </div>
      ))}
    </dl>
  );
}

function ConfigRow({ row }: { row: ConfigurationRow }) {
  const [open, setOpen] = useState(false);
  const runsHref = useMemo(() => {
    const params = new URLSearchParams();
    if (row.strategy_id) params.set("strategy_id", row.strategy_id);
    if (row.model_id) params.set("model_id", row.model_id);
    if (row.symbol) params.set("symbol", row.symbol);
    if (row.horizon_label) params.set("horizon_label", row.horizon_label);
    const query = params.toString();
    return query ? `/runs?${query}` : "/runs";
  }, [row]);

  return (
    <>
      <tr className="cursor-pointer hover:bg-surface/60" onClick={() => setOpen((value) => !value)}>
        <td>
          <span className={configKindBadgeClass(row.config_kind)}>{row.config_kind}</span>
        </td>
        <td>{row.symbol ?? "—"}</td>
        <td>{row.strategy_id ?? row.model_id ?? "—"}</td>
        <td>{row.horizon_label ?? row.resolution ?? "—"}</td>
        <td>{row.dataset_label ?? "—"}</td>
        <td className="font-mono text-xs text-muted">{row.id.slice(0, 8)}…</td>
        <td className="text-xs">{formatUtcTimestamp(row.created_at_utc)}</td>
        <td className="text-muted text-xs">{open ? "▲" : "▼"}</td>
      </tr>
      {open && (
        <tr>
          <td colSpan={8} className="!bg-surface/40 !p-4">
            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <h3 className="mb-2 text-sm font-medium text-white">Parameters</h3>
                <RecordFields value={row.parameters} />
              </div>
              <div>
                <h3 className="mb-2 text-sm font-medium text-white">Data context</h3>
                <RecordFields value={row.data_context} />
              </div>
            </div>
            <div className="mt-3">
              <Link href={runsHref} className="text-sm text-accent hover:underline">
                View matching runs →
              </Link>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function ConfigurationsPage() {
  const [kind, setKind] = useState("");
  const [symbolFilter, setSymbolFilter] = useState("");
  const datasetsQuery = useQuery({ queryKey: ["datasets"], queryFn: () => api.datasets() });

  const configsQuery = useQuery({
    queryKey: ["configs", kind],
    queryFn: () => api.configurations(kind || undefined),
  });

  const filteredRows = useMemo(() => {
    const rows = configsQuery.data ?? [];
    if (!symbolFilter) return rows;
    return rows.filter((row) => row.symbol === symbolFilter);
  }, [configsQuery.data, symbolFilter]);
  const symbols = useMemo(() => {
    const values = new Set<string>();
    for (const dataset of datasetsQuery.data ?? []) {
      if (dataset.symbol) values.add(dataset.symbol);
    }
    for (const row of configsQuery.data ?? []) {
      if (row.symbol) values.add(row.symbol);
    }
    return [...values].sort();
  }, [datasetsQuery.data, configsQuery.data]);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="4 · Review"
        title="Configurations"
        description="Snapshots of strategy, model, and experiment settings captured when runs are stored. Expand a row to inspect parameters and jump to matching runs."
        actions={
          <Link href="/runs" className="text-sm text-accent hover:underline">
            Browse runs
          </Link>
        }
      />

      <div className="flex flex-wrap items-end gap-3 text-sm">
        <div>
          <label className="mb-1 block text-xs text-muted">Kind</label>
          <SelectInput value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">All kinds</option>
            <option value="strategy">strategy</option>
            <option value="model">model</option>
            <option value="experiment">experiment</option>
          </SelectInput>
        </div>
        <div className="min-w-[10rem]">
          <label className="mb-1 block text-xs text-muted">Symbol</label>
          <SelectInput value={symbolFilter} onChange={(event) => setSymbolFilter(event.target.value)}>
            <option value="">All</option>
            {symbols.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </SelectInput>
        </div>
      </div>

      {configsQuery.isLoading && <p className="text-muted text-sm">Loading configurations…</p>}
      {configsQuery.isError && (
        <p className="text-red-400 text-sm">Failed to load configurations from the Lab API.</p>
      )}

      {!configsQuery.isLoading && filteredRows.length === 0 && (
        <p className="text-muted text-sm">
          No configuration snapshots yet. Run a backtest, ML job, or pipeline with store enabled (
          <code className="text-slate-200">TRADERBOT_STORE</code>).
        </p>
      )}

      {filteredRows.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-border">
          <table className="data">
            <thead>
              <tr>
                <th>Kind</th>
                <th>Symbol</th>
                <th>Strategy / model</th>
                <th>Horizon</th>
                <th>Dataset</th>
                <th>Config id</th>
                <th>Created</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {filteredRows.map((row) => (
                <ConfigRow key={row.id} row={row} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
