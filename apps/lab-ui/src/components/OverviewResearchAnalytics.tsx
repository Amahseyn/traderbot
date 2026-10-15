"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { DashboardStats } from "@/lib/api";
import { formatResolutionLabel, formatReturnPct, returnPctClassName } from "@/lib/format";

type RankRow = {
  key: string;
  label: ReactNode;
  n: number;
  best_return: number | null;
  avg_return: number | null;
  href?: string;
};

function LeaderboardTable({
  title,
  lead,
  nameHeader,
  rows,
  emptyMessage,
}: {
  title: string;
  lead: string;
  nameHeader: string;
  rows: RankRow[];
  emptyMessage: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-panel p-4 sm:p-5 h-full">
      <h2 className="section-title mb-1">{title}</h2>
      <p className="section-lead mb-4">{lead}</p>
      <div className="overflow-x-auto">
        <table className="data">
          <thead>
            <tr>
              <th>{nameHeader}</th>
              <th className="text-right">Runs</th>
              <th className="text-right">Avg return</th>
              <th className="text-right">Best return</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={4} className="text-muted text-sm">{emptyMessage}</td>
              </tr>
            )}
            {rows.map((row) => (
              <tr key={row.key}>
                <td className="font-medium">
                  {row.href ? (
                    <Link href={row.href} className="no-underline hover:text-accent">
                      {row.label}
                    </Link>
                  ) : (
                    row.label
                  )}
                </td>
                <td className="text-right tabular-nums">{row.n}</td>
                <td
                  className={`text-right font-mono text-sm tabular-nums ${returnPctClassName(
                    row.avg_return,
                  )}`}
                >
                  {formatReturnPct(row.avg_return)}
                </td>
                <td
                  className={`text-right font-mono text-sm tabular-nums ${returnPctClassName(
                    row.best_return,
                  )}`}
                >
                  {formatReturnPct(row.best_return)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function intervalDisplayLabel(intervalLabel: string): string {
  const formatted = formatResolutionLabel(intervalLabel);
  return formatted === intervalLabel ? intervalLabel : `${intervalLabel} (${formatted})`;
}

const EMPTY_BACKTEST_SUMMARY = {
  count: 0,
  avg_return: null,
  best_return: null,
  worst_return: null,
  positive_pct: null,
} as const;

export function OverviewResearchAnalytics({ stats }: { stats: DashboardStats }) {
  const summary = stats.backtest_summary ?? EMPTY_BACKTEST_SUMMARY;
  const strategyRows: RankRow[] = (stats.top_strategies ?? []).map((row) => ({
    key: row.strategy_id,
    label: row.strategy_id,
    n: row.n,
    best_return: row.best_return,
    avg_return: row.avg_return,
    href: `/runs?strategy_id=${encodeURIComponent(row.strategy_id)}`,
  }));

  const marketRows: RankRow[] = (stats.top_markets ?? []).map((row) => ({
    key: row.symbol,
    label: row.symbol,
    n: row.n,
    best_return: row.best_return,
    avg_return: row.avg_return,
    href: `/runs?symbol=${encodeURIComponent(row.symbol)}`,
  }));

  const intervalRows: RankRow[] = (stats.top_intervals ?? []).map((row) => ({
    key: row.interval_label,
    label: intervalDisplayLabel(row.interval_label),
    n: row.n,
    best_return: row.best_return,
    avg_return: row.avg_return,
  }));

  return (
    <div className="space-y-6">
      {summary.count > 0 && (
        <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <div className="stat-card">
            <div className="text-muted text-xs uppercase tracking-wide">Strategy backtests</div>
            <div className="text-2xl font-semibold mt-1 text-white tabular-nums">{summary.count}</div>
          </div>
          <div className="stat-card">
            <div className="text-muted text-xs uppercase tracking-wide">Mean return</div>
            <div
              className={`text-2xl font-semibold mt-1 tabular-nums ${returnPctClassName(
                summary.avg_return,
              )}`}
            >
              {formatReturnPct(summary.avg_return)}
            </div>
          </div>
          <div className="stat-card">
            <div className="text-muted text-xs uppercase tracking-wide">Best / worst</div>
            <div className="mt-1 text-sm font-mono tabular-nums">
              <span className={returnPctClassName(summary.best_return)}>
                {formatReturnPct(summary.best_return)}
              </span>
              <span className="text-muted"> / </span>
              <span className={returnPctClassName(summary.worst_return)}>
                {formatReturnPct(summary.worst_return)}
              </span>
            </div>
          </div>
          <div className="stat-card">
            <div className="text-muted text-xs uppercase tracking-wide">Positive runs</div>
            <div className="text-2xl font-semibold mt-1 text-white tabular-nums">
              {summary.positive_pct === null ? "—" : `${summary.positive_pct.toFixed(0)}%`}
            </div>
          </div>
        </section>
      )}

      <section className="grid gap-4 lg:grid-cols-2">
        <LeaderboardTable
          title="Top strategies"
          lead="Best peak return % across recorded backtests."
          nameHeader="Strategy"
          rows={strategyRows}
          emptyMessage="No strategy runs yet."
        />
        <LeaderboardTable
          title="Top markets"
          lead="Symbols ranked by average backtest return (ties broken by best run)."
          nameHeader="Symbol"
          rows={marketRows}
          emptyMessage="No market backtests yet."
        />
      </section>

      <section>
        <LeaderboardTable
          title="Intervals & horizons"
          lead="Bar size or horizon folder performance across strategy runs."
          nameHeader="Interval"
          rows={intervalRows}
          emptyMessage="No interval breakdown yet."
        />
      </section>
    </div>
  );
}
