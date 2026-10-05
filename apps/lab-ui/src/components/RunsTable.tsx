"use client";

import Link from "next/link";
import type { EvaluationRun } from "@/lib/api";
import {
  formatMoney,
  formatReturnPct,
  formatUtcTimestamp,
  returnPctClassName,
} from "@/lib/format";
import {
  runIntervalLabel,
  runListMetrics,
  runStrategyLabel,
  shortRunId,
} from "@/lib/runDisplay";

type RunsTableProps = {
  runs: EvaluationRun[];
  variant?: "compact" | "full";
};

export function RunsTable({ runs, variant = "full" }: RunsTableProps) {
  const isCompact = variant === "compact";

  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <table className="data runs-table">
        <thead>
          <tr>
            {!isCompact && <th className="w-[4.5rem]">ID</th>}
            <th>Kind</th>
            <th>Symbol</th>
            {!isCompact && <th>Dataset</th>}
            <th>Interval</th>
            <th>Strategy / model</th>
            <th className="text-right">Return</th>
            {!isCompact && <th className="text-right">Trades</th>}
            {!isCompact && <th className="text-right">Fees</th>}
            {!isCompact && <th className="text-right">Final equity</th>}
            {isCompact && <th className="text-right">Trades</th>}
            <th>Recorded</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => {
            const listed = runListMetrics(run);
            const isStrategy = run.run_kind === "strategy_backtest";
            const href = `/runs/${run.id}`;
            const returnLabel = isStrategy
              ? formatReturnPct(listed.returnPct)
              : typeof run.metrics.directional_accuracy === "number"
                ? `${(run.metrics.directional_accuracy * 100).toFixed(1)}% acc.`
                : "—";
            const returnClass = isStrategy ? returnPctClassName(listed.returnPct) : "text-sky-300";

            return (
              <tr key={run.id} className="group">
                {!isCompact && (
                  <td className="font-mono text-xs text-muted">
                    <Link href={href} className="no-underline hover:text-accent" title={run.id}>
                      {shortRunId(run.id)}
                    </Link>
                  </td>
                )}
                <td>
                  <span className={`badge ${isStrategy ? "badge-strategy" : "badge-model"}`}>
                    {isStrategy ? "Strategy" : "Model"}
                  </span>
                </td>
                <td className="font-medium text-white">{run.symbol ?? "—"}</td>
                {!isCompact && (
                  <td className="max-w-[12rem] truncate text-muted" title={run.dataset_label ?? undefined}>
                    {run.dataset_label ?? "—"}
                  </td>
                )}
                <td className="whitespace-nowrap text-muted">{runIntervalLabel(run)}</td>
                <td className="max-w-[10rem] truncate font-medium" title={runStrategyLabel(run)}>
                  {runStrategyLabel(run)}
                </td>
                <td className={`text-right font-mono text-sm tabular-nums ${returnClass}`}>
                  {returnLabel}
                </td>
                {!isCompact && (
                  <td className="text-right tabular-nums">{listed.trades ?? "—"}</td>
                )}
                {!isCompact && (
                  <td className="text-right font-mono text-xs tabular-nums text-muted">
                    {listed.totalFees != null ? formatMoney(listed.totalFees) : "—"}
                  </td>
                )}
                {!isCompact && (
                  <td className="text-right font-mono text-xs tabular-nums">
                    {listed.finalEquity != null ? formatMoney(listed.finalEquity) : "—"}
                  </td>
                )}
                {isCompact && (
                  <td className="text-right tabular-nums text-muted">{listed.trades ?? "—"}</td>
                )}
                <td className="whitespace-nowrap">
                  <Link
                    href={href}
                    className="font-medium text-accent no-underline group-hover:underline"
                  >
                    {formatUtcTimestamp(run.created_at_utc)}
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
