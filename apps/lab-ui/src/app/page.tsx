"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api, API_BASE } from "@/lib/api";
import { formatUtcTimestamp } from "@/lib/format";
import { WorkflowCards } from "@/components/WorkflowCards";
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

  return (
    <div className="space-y-8">
      <PageHeader
        title="Research overview"
        description="Export data, run strategies in Lab, then inspect runs and configs."
        actions={
          <Link href="/experiments">
            <Button>Open Lab</Button>
          </Link>
        }
      />

      <WorkflowCards />

      <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {(
          [
            { label: "Runs", value: stats.run_count, href: "/runs" },
            { label: "Configurations", value: stats.config_count, href: "/configs" },
            { label: "Compare sessions", value: stats.compare_count, href: "/experiments#compares" },
            { label: "Experiment configs", value: stats.experiment_count, href: "/experiments#pipelines" },
          ] as const
        ).map(({ label, value, href }) => (
          <Link key={label} href={href} className="stat-card block">
            <div className="text-muted text-xs uppercase tracking-wide">{label}</div>
            <div className="text-2xl font-semibold mt-1 text-white">{value}</div>
          </Link>
        ))}
      </section>

      <section className="grid gap-6 md:grid-cols-2">
        <div className="rounded-xl border border-border bg-panel p-4">
          <h2 className="text-lg font-medium mb-2 text-white">Top strategies (return %)</h2>
          <table className="data">
            <thead>
              <tr>
                <th>Strategy</th>
                <th>Runs</th>
                <th>Best</th>
              </tr>
            </thead>
            <tbody>
              {stats.top_strategies.map((row) => (
                <tr key={row.strategy_id}>
                  <td>{row.strategy_id}</td>
                  <td>{row.n}</td>
                  <td>{row.best_return ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-xl border border-border bg-panel p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="text-lg font-medium text-white">Recent runs</h2>
          <Link href="/runs" className="text-sm text-accent hover:underline">View all</Link>
        </div>
        <table className="data">
          <thead>
            <tr>
              <th>Kind</th>
              <th>Symbol</th>
              <th>Strategy / model</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {(runsQuery.data ?? []).length === 0 && !runsQuery.isLoading && (
              <tr>
                <td colSpan={4} className="text-muted text-sm">
                  No runs in the catalog yet.{" "}
                  <Link href="/data" className="text-accent hover:underline">
                    Export data
                  </Link>{" "}
                  or{" "}
                  <Link href="/experiments" className="text-accent hover:underline">
                    open Lab
                  </Link>
                  .
                </td>
              </tr>
            )}
            {(runsQuery.data ?? []).map((run) => (
              <tr key={run.id}>
                <td>
                  <span
                    className={`badge ${
                      run.run_kind === "strategy_backtest" ? "badge-strategy" : "badge-model"
                    }`}
                  >
                    {run.run_kind === "strategy_backtest" ? "strategy" : "model"}
                  </span>
                </td>
                <td>{run.symbol ?? "—"}</td>
                <td>{run.strategy_id ?? run.model_id ?? "—"}</td>
                <td>
                  <Link href={`/runs/${run.id}`}>{formatUtcTimestamp(run.created_at_utc)}</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
