"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api, API_BASE } from "@/lib/api";
import { WorkflowCards } from "@/components/WorkflowCards";
import { OverviewResearchAnalytics } from "@/components/OverviewResearchAnalytics";
import { RunsTable } from "@/components/RunsTable";
import { Button } from "@/components/ui/Button";
import { Page } from "@/components/ui/Page";
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
      <Page>
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
      </Page>
    );
  }

  const stats = statsQuery.data!;
  const recentRuns = runsQuery.data ?? [];

  return (
    <Page>
      <PageHeader
        eyebrow="Console"
        title="Research overview"
        description="Quantitative strategy research, market data ingestion, and execution archive."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Link href="/custom">
              <Button variant="secondary">Custom pipeline</Button>
            </Link>
            <Link href="/marketcap">
              <Button>Market Cap</Button>
            </Link>
          </div>
        }
      />

      <WorkflowCards />

      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3" aria-label="Core metrics">
        <Link href="/runs" className="stat-card group block">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-muted">Catalog Runs</span>
            <div className="flex h-7 w-7 items-center justify-center rounded border border-border bg-panel-elevated text-zinc-400 transition-colors duration-150 group-hover:border-border-bright group-hover:text-accent">
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
                <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" strokeLinecap="round" />
              </svg>
            </div>
          </div>
          <div className="mt-2 text-2xl font-bold tracking-tight text-white tabular-nums sm:text-3xl">
            {stats.run_count}
          </div>
          <div className="mt-2 flex items-center justify-between text-xs text-muted">
            <span>Historical backtests</span>
            <span className="font-mono text-[10px] text-zinc-500 group-hover:text-accent">VIEW</span>
          </div>
        </Link>

        <Link href="/custom#quick-jobs" className="stat-card group block">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-muted">Compare Sessions</span>
            <div className="flex h-7 w-7 items-center justify-center rounded border border-border bg-panel-elevated text-zinc-400 transition-colors duration-150 group-hover:border-border-bright group-hover:text-accent">
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
                <path d="M16 3h5v5M4 20L21 3M21 16v5h-5M15 15l6 6M4 4l5 5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          </div>
          <div className="mt-2 text-2xl font-bold tracking-tight text-white tabular-nums sm:text-3xl">
            {stats.compare_count}
          </div>
          <div className="mt-2 flex items-center justify-between text-xs text-muted">
            <span>Multi-strategy matrices</span>
            <span className="font-mono text-[10px] text-zinc-500 group-hover:text-accent">VIEW</span>
          </div>
        </Link>

        <Link href="/optimizer" className="stat-card group block">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-muted">Parameter Sweeps</span>
            <div className="flex h-7 w-7 items-center justify-center rounded border border-border bg-panel-elevated text-zinc-400 transition-colors duration-150 group-hover:border-border-bright group-hover:text-accent">
              <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
                <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" strokeLinecap="round" />
                <circle cx="12" cy="12" r="4" />
              </svg>
            </div>
          </div>
          <div className="mt-2 text-2xl font-bold tracking-tight text-white tabular-nums sm:text-3xl">
            {stats.sweep_count}
          </div>
          <div className="mt-2 flex items-center justify-between text-xs text-muted">
            <span>Optuna tuning & sweeps</span>
            <span className="font-mono text-[10px] text-zinc-500 group-hover:text-accent">VIEW</span>
          </div>
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
                <Link href="/marketcap"><Button>Explore markets</Button></Link>
              </div>
            }
          />
        )}
        {recentRuns.length > 0 && <RunsTable runs={recentRuns} variant="compact" />}
      </section>
    </Page>
  );
}
