"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { LiveTradingChart } from "@/components/LiveTradingChart";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { api, type JobRow } from "@/lib/api";
import {
  isActiveTerminalJobStatus,
  liveSessionFromJob,
  liveSessionPairLabel,
  liveSessionSortKey,
  liveSessionSubtitle,
  type LiveTerminalSession,
} from "@/lib/liveSession";

const TERMINAL_JOB_TYPES = new Set(["terminal-once", "terminal-live", "terminal-replay"]);
const LIVE_JOB_POLL_MS = 500;
const MAX_WATCHED_SESSIONS = 24;

type LiveSessionsChartsProps = {
  watchedJobIds: string[];
  onWatchedJobIdsChange: (jobIds: string[]) => void;
  onMergeWatchedJobIds: (jobIds: string[]) => void;
  focusedJobId: string | null;
  onFocusJob: (jobId: string) => void;
};

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

export function LiveSessionsCharts({
  watchedJobIds,
  onWatchedJobIdsChange,
  onMergeWatchedJobIds,
  focusedJobId,
  onFocusJob,
}: LiveSessionsChartsProps) {
  const [showCompleted, setShowCompleted] = useState(true);

  const jobsQuery = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api.jobs(80),
    refetchInterval: (query) => {
      const rows = query.state.data ?? [];
      return rows.some(
        (job) => TERMINAL_JOB_TYPES.has(job.job_type) && isActiveTerminalJobStatus(job.status),
      )
        ? 2000
        : 20000;
    },
  });

  useEffect(() => {
    const terminalJobs = (jobsQuery.data ?? []).filter((job) => TERMINAL_JOB_TYPES.has(job.job_type));
    const activeIds = terminalJobs
      .filter((job) => isActiveTerminalJobStatus(job.status))
      .map((job) => job.id);
    if (activeIds.length === 0) {
      return;
    }
    onMergeWatchedJobIds(activeIds);
  }, [jobsQuery.data, onMergeWatchedJobIds]);

  const jobDetailQueries = useQueries({
    queries: watchedJobIds.map((jobId) => ({
      queryKey: ["job", jobId],
      queryFn: () => api.job(jobId),
      staleTime: 0,
      refetchInterval: (query: { state: { data?: JobRow } }) => {
        const status = query.state.data?.status ?? "";
        return isActiveTerminalJobStatus(status) ? LIVE_JOB_POLL_MS : false;
      },
    })),
  });

  const sessions = useMemo(() => {
    const rows: LiveTerminalSession[] = [];
    for (const result of jobDetailQueries) {
      if (result.data) {
        rows.push(liveSessionFromJob(result.data));
      }
    }
    rows.sort((left, right) => liveSessionSortKey(left).localeCompare(liveSessionSortKey(right)));
    return rows;
  }, [jobDetailQueries]);

  const visibleSessions = useMemo(
    () =>
      showCompleted
        ? sessions
        : sessions.filter((session) => isActiveTerminalJobStatus(session.status)),
    [sessions, showCompleted],
  );

  const activeCount = sessions.filter((session) => isActiveTerminalJobStatus(session.status)).length;

  function dismissSession(jobId: string) {
    onWatchedJobIdsChange(watchedJobIds.filter((id) => id !== jobId));
    if (focusedJobId === jobId) {
      const next = watchedJobIds.find((id) => id !== jobId);
      if (next) {
        onFocusJob(next);
      }
    }
  }

  return (
    <Card
      title="Live session charts"
      description="One chart per trading job — each polls its own market, horizon, and log while running."
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-surface px-2.5 py-1 text-xs text-muted ring-1 ring-border">
            {activeCount} active · {sessions.length} shown
          </span>
          <Button
            type="button"
            variant="secondary"
            className="text-xs"
            onClick={() => setShowCompleted((value) => !value)}
          >
            {showCompleted ? "Hide finished" : "Show finished"}
          </Button>
        </div>
      }
    >
      {watchedJobIds.length === 0 && (
        <p className="text-sm text-muted">
          Start a session above to see candles and trade markers here. Multi-run starts several charts
          at once.
        </p>
      )}

      {watchedJobIds.length > 0 && visibleSessions.length === 0 && (
        <p className="text-sm text-muted">Loading session data…</p>
      )}

      {visibleSessions.length > 0 && (
        <div
          className={`grid gap-6 ${
            visibleSessions.length > 1 ? "lg:grid-cols-2" : "grid-cols-1"
          }`}
        >
          {visibleSessions.map((session) => (
            <LiveTradingChart
              key={session.jobId}
              jobId={session.jobId}
              src={session.src}
              dst={session.dst}
              interval={session.interval}
              symbol={session.marketSymbol}
              logText={session.logText}
              refreshActive={isActiveTerminalJobStatus(session.status)}
              jobStatus={session.status}
              strategyId={session.strategyId}
              liveOrders={session.liveOrders}
              title={liveSessionPairLabel(session)}
              subtitle={liveSessionSubtitle(session)}
              focused={focusedJobId === session.jobId}
              onFocus={() => onFocusJob(session.jobId)}
              onDismiss={() => dismissSession(session.jobId)}
            />
          ))}
        </div>
      )}
    </Card>
  );
}
