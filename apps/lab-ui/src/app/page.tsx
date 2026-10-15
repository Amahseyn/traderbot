"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api, API_BASE } from "@/lib/api";
import { WorkflowCards } from "@/components/WorkflowCards";
import { OverviewResearchAnalytics } from "@/components/OverviewResearchAnalytics";
import { RunsTable } from "@/components/RunsTable";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, PageSkeleton, TableSkeleton } from "@/components/ui/States";

export default function DashboardPage() {
  const statsQuery = useQuery({ queryKey: ["stats"], queryFn: api.stats });
  const runsQuery = useQuery({
    queryKey: ["runs", "recent"],
    queryFn: () => api.runs("?limit=12"),
  });

  if (statsQuery.isLoading) {
    return <PageSkeleton />;
  }
  if (statsQuery.isError) {
    return (
      <div className="space-y-6">
        <PageHeader title="Research overview" />
        <ErrorState
          title={`Cannot reach Lab API (${API_BASE})`}
          error="Start the stack with ./run-lab.sh, or run ./run-lab-api.sh in another terminal."
          action={
            <Button variant="secondary" onClick={() => statsQuery.refetch()}>
              Retry
            </Button>
          }
        />
      </div>
    );
  }

  const stats = statsQuery.data!;
  const recentRuns = runsQuery.data ?? [];

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Overview"
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

      <OverviewResearchAnalytics stats={stats} />

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
        {runsQuery.isLoading && <TableSkeleton rows={5} />}
        {runsQuery.isError && <ErrorState title="Failed to load recent runs" error={runsQuery.error} />}
        {recentRuns.length === 0 && runsQuery.isSuccess && (
          <EmptyState
            title="No runs yet"
            description="Export market data, then run a backtest from Custom research."
            action={
              <div className="flex flex-wrap justify-center gap-2">
                <Link href="/data"><Button variant="secondary">Export data</Button></Link>
                <Link href="/custom"><Button>Start research</Button></Link>
              </div>
            }
          />
        )}
        {recentRuns.length > 0 && <RunsTable runs={recentRuns} variant="compact" />}
      </section>
    </div>
  );
}
