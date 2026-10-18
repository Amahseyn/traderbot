"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Field, TextInput } from "@/components/ui/Field";
import { api, type SweepSession } from "@/lib/api";
import { ErrorState, TableSkeleton } from "@/components/ui/States";
import { formatUtcTimestamp } from "@/lib/format";

function metricPct(metrics: Record<string, unknown>, key: string): string {
  const raw = metrics[key];
  if (raw == null || raw === "") return "—";
  const value = Number(raw);
  if (!Number.isFinite(value)) return "—";
  return `${value.toFixed(2)}%`;
}

function paramPreview(params: Record<string, unknown>, max = 3): string {
  const entries = Object.entries(params);
  if (entries.length === 0) return "—";
  const shown = entries.slice(0, max).map(([name, value]) => `${name}=${String(value)}`);
  const suffix = entries.length > max ? ` +${entries.length - max}` : "";
  return shown.join(", ") + suffix;
}

export function OptimizerSweepsTable({ limit = 25 }: { limit?: number }) {
  const [marketFilter, setMarketFilter] = useState("");
  const sweepsQuery = useQuery({
    queryKey: ["sweeps", limit],
    queryFn: () => api.sweeps(`?limit=${limit}`),
    staleTime: 15_000,
  });

  const allRows = sweepsQuery.data ?? [];
  const needle = marketFilter.trim().toLowerCase();
  const rows = useMemo(() => {
    if (!needle) {
      return allRows;
    }
    return allRows.filter((row) => {
      const symbol = (row.symbol ?? "").toLowerCase();
      const strategy = row.strategy_id.toLowerCase();
      return symbol.includes(needle) || strategy.includes(needle);
    });
  }, [allRows, needle]);

  if (sweepsQuery.isLoading) {
    return <TableSkeleton rows={5} />;
  }
  if (sweepsQuery.isError) {
    return <ErrorState title="Could not load sweeps" error={sweepsQuery.error} hintAuth={false} />;
  }

  if (allRows.length === 0) {
    return (
      <p className="text-sm text-muted">
        No stored sweeps yet. Run an Optuna job above — winners are saved per strategy and dataset
        (symbol, resolution, horizon folder).
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="max-w-xs">
        <Field label="Filter sweeps" hint="Symbol or strategy id">
          <TextInput
            placeholder="e.g. BTC, ema"
            value={marketFilter}
            onChange={(event) => setMarketFilter(event.target.value)}
            autoComplete="off"
          />
        </Field>
      </div>
      {rows.length === 0 && needle ? (
        <p className="text-sm text-muted">No sweeps match &ldquo;{marketFilter.trim()}&rdquo;.</p>
      ) : null}
      <div className="overflow-x-auto rounded-lg border border-border">
      <table className="data w-full text-sm">
        <thead>
          <tr>
            <th>When</th>
            <th>Strategy</th>
            <th>Market</th>
            <th>Validation</th>
            <th>Holdout</th>
            <th>Best params</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row: SweepSession) => {
            const metrics = row.best_metrics ?? {};
            const label = [
              row.symbol,
              row.resolution ? `${row.resolution}m` : null,
              row.horizon_label,
            ]
              .filter(Boolean)
              .join(" · ");
            return (
              <tr key={row.id}>
                <td className="whitespace-nowrap text-muted">
                  {formatUtcTimestamp(row.created_at_utc)}
                </td>
                <td>
                  <Link href="/strategies" className="text-accent hover:underline">
                    {row.strategy_id}
                  </Link>
                </td>
                <td className="font-mono text-xs">{label || "—"}</td>
                <td>{metricPct(metrics, "return_pct")}</td>
                <td>{metricPct(metrics, "holdout_return_pct")}</td>
                <td className="max-w-[14rem] truncate font-mono text-xs text-muted" title={paramPreview(row.best_params, 20)}>
                  {paramPreview(row.best_params)}
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
