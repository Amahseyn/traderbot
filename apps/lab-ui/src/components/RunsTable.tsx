"use client";

import Link from "next/link";
import type { EvaluationRun } from "@/lib/api";
import {
  formatMoney,
  formatRelativeTime,
  formatReturnPct,
  formatUtcTimestamp,
  formatWinRate,
  returnPctClassName,
} from "@/lib/format";
import {
  isRunOptimized,
  runIntervalLabel,
  runListMetrics,
  runParametersList,
  runParametersSummary,
  runStrategyLabel,
  shortRunId,
} from "@/lib/runDisplay";

type RunsTableProps = {
  runs: EvaluationRun[];
  variant?: "compact" | "full";
  sortBy?: string;
  onSort?: (sortBy: string) => void;
};

export function RunsTable({ runs, variant = "full", sortBy, onSort }: RunsTableProps) {
  const isCompact = variant === "compact";

  const renderSortableTh = (
    label: string,
    colKey: "return" | "win_rate" | "trades" | "equity" | "created_at",
    align: "left" | "right" = "left",
    extraClass = "",
  ) => {
    if (!onSort) {
      return (
        <th className={`${align === "right" ? "text-right" : ""} ${extraClass}`}>
          {label}
        </th>
      );
    }
    const isDesc = sortBy === `${colKey}_desc`;
    const isAsc = sortBy === `${colKey}_asc`;
    const isActive = isDesc || isAsc;
    const nextSort =
      colKey === "created_at"
        ? isDesc
          ? "created_at_asc"
          : "created_at_desc"
        : isDesc
          ? `${colKey}_asc`
          : `${colKey}_desc`;

    return (
      <th
        aria-sort={isDesc ? "descending" : isAsc ? "ascending" : "none"}
        className={`${align === "right" ? "text-right" : ""} ${extraClass}`}
      >
        <button
          type="button"
          onClick={() => onSort(nextSort)}
          className={`inline-flex items-center gap-1 font-medium hover:text-white transition-colors duration-150 focus:outline-none focus-visible:ring-1 focus-visible:ring-accent rounded ${
            align === "right" ? "ml-auto" : ""
          } ${isActive ? "text-accent" : "text-muted"}`}
          title={`Sort by ${label} (${isDesc ? "descending" : isAsc ? "ascending" : "click to sort"})`}
        >
          <span>{label}</span>
          <span className="font-mono text-[10px] select-none" aria-hidden="true">
            {isDesc ? "↓" : isAsc ? "↑" : "↕"}
          </span>
        </button>
      </th>
    );
  };

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
            <th>Optimizer</th>
            {!isCompact && <th>Parameters</th>}
            {renderSortableTh("Return", "return", "right")}
            {renderSortableTh("Win rate", "win_rate", "right")}
            {!isCompact && renderSortableTh("Trades", "trades", "right")}
            {!isCompact && <th className="text-right">Fees</th>}
            {!isCompact && renderSortableTh("Final equity", "equity", "right")}
            {isCompact && renderSortableTh("Trades", "trades", "right")}
            {renderSortableTh("Recorded", "created_at", "left")}
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => {
            const listed = runListMetrics(run);
            const isStrategy = run.run_kind === "strategy_backtest";
            const isOptimized = isRunOptimized(run);
            const paramEntries = runParametersList(run);
            const paramsSummary = runParametersSummary(run);
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
                <td>
                  <span
                    className={`badge ${
                      isOptimized
                        ? "badge-strategy"
                        : "border border-border bg-surface text-muted"
                    }`}
                    title={
                      isOptimized
                        ? "Optimizer enabled (tuned parameters applied)"
                        : "Default parameters (optimizer not applied)"
                    }
                  >
                    {isOptimized ? "Optimized" : "Default"}
                  </span>
                </td>
                {!isCompact && (
                  <td className="min-w-[16rem] whitespace-normal py-2" title={paramsSummary}>
                    {paramEntries.length > 0 ? (
                      <div className="flex flex-wrap items-center gap-1.5">
                        {paramEntries.map(({ key, value }) => (
                          <span
                            key={key}
                            className="inline-flex items-center gap-1 rounded border border-border/80 bg-surface/80 px-1.5 py-0.5 font-mono text-[11px] text-white"
                          >
                            <span className="text-muted">{key}:</span>
                            <span className="font-medium text-white">{String(value)}</span>
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span className="font-mono text-xs text-muted">—</span>
                    )}
                  </td>
                )}
                <td className={`text-right font-mono text-sm tabular-nums ${returnClass}`}>
                  {returnLabel}
                </td>
                <td className="text-right font-mono text-xs tabular-nums text-white">
                  {formatWinRate(listed.winRatePct)}
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
                    title={formatUtcTimestamp(run.created_at_utc)}
                  >
                    {formatRelativeTime(run.created_at_utc)}
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
