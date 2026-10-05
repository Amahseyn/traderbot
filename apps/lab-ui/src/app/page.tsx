"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api, API_BASE } from "@/lib/api";
import { formatReturnPct, returnPctClassName } from "@/lib/format";
import { WorkflowCards } from "@/components/WorkflowCards";
import { RunsTable } from "@/components/RunsTable";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";

export default function DashboardPage() {
  const statsQuery = useQuery({ queryKey: ["stats"], queryFn: api.stats });
  const runsQuery = useQuery({
    queryKey: ["runs", "recent"],
    queryFn: () => api.runs("?limit=12"),
  });

  if (statsQuery.isLoading) {
    return <p className="text-muted">Loading dashboard…</p>;
  }
  if (statsQuery.isError) {
    return (
      <p className="text-red-400">
        Cannot reach Lab API ({API_BASE}). Start the stack with{" "}
        <code className="text-slate-200">./run-lab.sh</code> or run{" "}
        <code className="text-slate-200">./run-lab-api.sh</code> in another terminal.
      </p>
    );
  }

  const stats = statsQuery.data!;
  const recentRuns = runsQuery.data ?? [];

  return (
    <div className="space-y-8">
      <PageHeader
        title="Research overview"
        description="Export market data, run backtests from Custom research, then review runs and trade logs."
        actions={
          <Link href="/custom">
            <Button>New research job</Button>
          </Link>
        }
      />

      <WorkflowCards />

      <section className="grid grid-cols-2 gap-4 md:grid-cols-3">
        <Link href="/runs" className="stat-card block">
          <div className="text-muted text-xs uppercase tracking-wide">Runs</div>
          <div className="text-2xl font-semibold mt-1 text-white">{stats.run_count}</div>
        </Link>
        <Link href="/data" className="stat-card block">
          <div className="text-muted text-xs uppercase tracking-wide">Compare sessions</div>
          <div className="text-2xl font-semibold mt-1 text-white">{stats.compare_count}</div>
        </Link>
        <Link href="/custom" className="stat-card block">
          <div className="text-muted text-xs uppercase tracking-wide">Parameter sweeps</div>
          <div className="text-2xl font-semibold mt-1 text-white">{stats.sweep_count}</div>
        </Link>
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-border bg-panel p-4">
          <h2 className="section-title mb-1">Top strategies</h2>
          <p className="section-lead mb-4">Best return % seen across recorded backtests.</p>
          <table className="data">
            <thead>
              <tr>
                <th>Strategy</th>
                <th className="text-right">Runs</th>
                <th className="text-right">Best return</th>
              </tr>
            </thead>
            <tbody>
              {stats.top_strategies.length === 0 && (
                <tr>
                  <td colSpan={3} className="text-muted text-sm">No strategy runs yet.</td>
                </tr>
              )}
              {stats.top_strategies.map((row) => (
                <tr key={row.strategy_id}>
                  <td className="font-medium">{row.strategy_id}</td>
                  <td className="text-right tabular-nums">{row.n}</td>
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
      </section>

      <section className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="section-title">Recent runs</h2>
            <p className="section-lead mt-1">Latest backtests synced into the catalog.</p>
          </div>
          <Link href="/runs" className="text-sm text-accent hover:underline shrink-0">
            View all
          </Link>
        </div>
        {recentRuns.length === 0 && !runsQuery.isLoading && (
          <p className="text-muted text-sm">
            No runs yet.{" "}
            <Link href="/data" className="text-accent hover:underline">
              Export data
            </Link>{" "}
            or{" "}
            <Link href="/custom" className="text-accent hover:underline">
              start Custom research
            </Link>
            .
          </p>
        )}
        {recentRuns.length > 0 && <RunsTable runs={recentRuns} variant="compact" />}
      </section>
    </div>
  );
}
