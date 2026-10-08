"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useCallback, useState } from "react";
import { JobMonitor } from "@/components/JobMonitor";
import { LiveSessionsCharts } from "@/components/LiveSessionsCharts";
import { LiveTradingPanel } from "@/components/LiveTradingPanel";
import { RiskStatePanel } from "@/components/RiskStatePanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { api } from "@/lib/api";

const TERMINAL_JOB_TYPES = ["terminal-once", "terminal-live", "terminal-replay"];
const MAX_WATCHED_SESSIONS = 24;

function mergeWatchedIds(current: string[], additions: string[]): string[] {
  const merged = [...additions, ...current];
  const seen = new Set<string>();
  const ordered: string[] = [];
  for (const jobId of merged) {
    if (!jobId || seen.has(jobId)) {
      continue;
    }
    seen.add(jobId);
    ordered.push(jobId);
  }
  return ordered.slice(0, MAX_WATCHED_SESSIONS);
}

export default function LiveTradingPage() {
  const [focusedJobId, setFocusedJobId] = useState<string | null>(null);
  const [watchedJobIds, setWatchedJobIds] = useState<string[]>([]);
  const authQuery = useQuery({ queryKey: ["auth-status"], queryFn: api.authStatus });

  const handleJobsStarted = useCallback((jobIds: string[]) => {
    if (jobIds.length === 0) {
      return;
    }
    setWatchedJobIds((current) => mergeWatchedIds(current, jobIds));
    setFocusedJobId(jobIds[jobIds.length - 1] ?? null);
  }, []);

  const mergeWatched = useCallback((jobIds: string[]) => {
    setWatchedJobIds((current) => mergeWatchedIds(current, jobIds));
  }, []);

  const keysReady = authQuery.data?.api_keys_configured === true;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Live trading"
        description="Run one or many sessions in parallel — each job gets its own chart, log stream, and Nobitex candle feed."
        actions={
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                keysReady
                  ? "bg-emerald-900/40 text-emerald-200 ring-1 ring-emerald-500/30"
                  : "bg-amber-900/30 text-amber-100 ring-1 ring-amber-500/25"
              }`}
            >
              {keysReady ? "API keys configured" : "Paper test ready without keys"}
            </span>
            <Link href="/settings" className="text-accent hover:underline">
              Credentials
            </Link>
          </div>
        }
      />

      <RiskStatePanel />

      <LiveTradingPanel onJobsStarted={handleJobsStarted} />

      <LiveSessionsCharts
        watchedJobIds={watchedJobIds}
        onWatchedJobIdsChange={setWatchedJobIds}
        onMergeWatchedJobIds={mergeWatched}
        focusedJobId={focusedJobId}
        onFocusJob={setFocusedJobId}
      />

      <JobMonitor
        activeJobId={focusedJobId}
        onSelectJob={(jobId) => {
          setFocusedJobId(jobId);
          setWatchedJobIds((current) => mergeWatchedIds(current, [jobId]));
        }}
        jobTypeFilter={TERMINAL_JOB_TYPES}
        logMode="full"
        alwaysShowLogPanel
        recentJobsTitle="Recent trading jobs"
        recentJobsDescription="Each run is a separate job — start another anytime; statuses refresh for every active session."
      />
    </div>
  );
}
