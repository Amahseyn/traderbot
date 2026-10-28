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
    <div className="rounded-lg border border-border bg-panel p-4 h-full flex flex-col justify-between">
      <div>
        <h2 className="text-sm font-semibold tracking-tight text-white mb-0.5">{title}</h2>
        <p className="text-xs leading-relaxed text-muted mb-3">{lead}</p>
        <div className="overflow-x-auto rounded border border-border">
          <table className="data">
            <thead>
              <tr>
                <th className="w-10 text-center">#</th>
                <th>{nameHeader}</th>
                <th className="text-right">Runs</th>
                <th className="text-right">Avg return</th>
                <th className="text-right">Best return</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr>
                  <td colSpan={5} className="text-muted text-xs py-4 text-center">
                    {emptyMessage}
                  </td>
                </tr>
              )}
              {rows.map((row, index) => (
                <tr key={row.key} className="transition-colors duration-150 hover:bg-panel-elevated/70">
                  <td className="text-center font-mono text-xs text-muted">
                    {index + 1}
                  </td>
                  <td className="font-medium text-white">
                    {row.href ? (
                      <Link href={row.href} className="no-underline text-white hover:text-accent transition-colors duration-150">
                        {row.label}
                      </Link>
                    ) : (
                      row.label
                    )}
                  </td>
                  <td className="text-right tabular-nums text-muted">{row.n}</td>
                  <td
                    className={`text-right font-mono text-xs tabular-nums ${returnPctClassName(
                      row.avg_return,
                    )}`}
                  >
                    {formatReturnPct(row.avg_return)}
                  </td>
                  <td
                    className={`text-right font-mono text-xs tabular-nums font-semibold ${returnPctClassName(
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
    <div className="space-y-4">
      {summary.count > 0 && (
        <section className="grid grid-cols-2 gap-3 md:grid-cols-4" aria-label="Research summary">
          <div className="stat-card">
            <div className="flex items-center justify-between">
              <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-muted">Backtests</span>
              <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden />
            </div>
            <div className="mt-1.5 text-2xl font-bold tracking-tight text-white tabular-nums">
              {summary.count}
            </div>
            <div className="mt-1 text-xs text-muted">Completed runs</div>
          </div>

          <div className="stat-card">
            <div className="flex items-center justify-between">
              <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-muted">Mean Return</span>
              <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden />
            </div>
            <div
              className={`mt-1.5 text-2xl font-bold tracking-tight tabular-nums ${returnPctClassName(
                summary.avg_return,
              )}`}
            >
              {formatReturnPct(summary.avg_return)}
            </div>
            <div className="mt-1 text-xs text-muted">Across all strategies</div>
          </div>

          <div className="stat-card">
            <div className="flex items-center justify-between">
              <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-muted">Best / Worst</span>
              <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden />
            </div>
            <div className="mt-1.5 text-xs font-mono font-semibold tabular-nums">
              <span className={returnPctClassName(summary.best_return)}>
                {formatReturnPct(summary.best_return)}
              </span>
              <span className="text-muted font-normal"> / </span>
              <span className={returnPctClassName(summary.worst_return)}>
                {formatReturnPct(summary.worst_return)}
              </span>
            </div>
            <div className="mt-2 text-xs text-muted">Peak vs max drawdown</div>
          </div>

          <div className="stat-card">
            <div className="flex items-center justify-between">
              <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-muted">Win Rate</span>
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" aria-hidden />
            </div>
            <div className="mt-1.5 text-2xl font-bold tracking-tight text-white tabular-nums">
              {summary.positive_pct === null ? "—" : `${summary.positive_pct.toFixed(1)}%`}
            </div>
            <div className="mt-1 text-xs text-muted">Profitable strategies</div>
          </div>
        </section>
      )}

      <section className="grid gap-3 lg:grid-cols-2">
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
