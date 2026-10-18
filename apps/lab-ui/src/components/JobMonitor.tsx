"use client";

import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type JobRow } from "@/lib/api";
import { formatResolutionLabel, formatUtcTimestamp } from "@/lib/format";
import { filterJobLogText } from "@/lib/jobLog";
import { extractDiscoveryErrorLogLines } from "@/lib/opportunityDiscoveryLog";
import { formatLiveLogPhaseSummary, summarizeLiveJobLog } from "@/lib/liveLog";
import { liveSessionMetricsFromJob } from "@/lib/liveSession";
import { formatMoney } from "@/lib/format";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { EmptyState, ErrorState, Skeleton, TableSkeleton } from "@/components/ui/States";

const LIVE_JOB_POLL_MS = 500;
const LIVE_JOBS_LIST_POLL_MS = 1000;

type JobsSortKey = "time-desc" | "time-asc" | "return-desc" | "return-asc";

type JobMonitorProps = {
  activeJobId: string | null;
  onSelectJob?: (jobId: string) => void;
  /** When set, only these job types appear in the recent jobs table. */
  jobTypeFilter?: string[];
  recentJobsTitle?: string;
  recentJobsDescription?: string;
  /** Tall log panel with raw output (live trading). */
  logMode?: "default" | "full";
  /** Show the log card even when no job is selected (full mode placeholder). */
  alwaysShowLogPanel?: boolean;
  /** Render inside a parent Card (no nested Cards; jobs table above log). */
  embedded?: boolean;
  /** Add session to watched charts when selecting a job from the table. */
  onWatchJob?: (jobId: string) => void;
  /** Extra columns: rank, strategy, session return %, equity, trades; sorts by return. */
  showSessionMetrics?: boolean;
  /** Max jobs loaded from the API (default 50). */
  jobsListLimit?: number;
  /** When set, paginate the jobs table with this many rows per page. */
  jobsPageSize?: number;
};

function isActiveJob(job: JobRow): boolean {
  return job.status === "queued" || job.status === "running";
}

function canRestartJob(job: JobRow): boolean {
  return !isActiveJob(job) && Object.keys(job.payload ?? {}).length > 0;
}

function compareJobsForSort(left: JobRow, right: JobRow, sort: JobsSortKey): number {
  const leftLive = Boolean(left.payload?.live);
  const rightLive = Boolean(right.payload?.live);
  if (leftLive !== rightLive) {
    return leftLive ? 1 : -1;
  }

  if (sort === "time-desc" || sort === "time-asc") {
    const cmp = right.created_at_utc.localeCompare(left.created_at_utc);
    return sort === "time-desc" ? cmp : -cmp;
  }

  const leftReturn = liveSessionMetricsFromJob(left).sessionReturnPct ?? -Infinity;
  const rightReturn = liveSessionMetricsFromJob(right).sessionReturnPct ?? -Infinity;
  if (rightReturn !== leftReturn) {
    return sort === "return-desc" ? rightReturn - leftReturn : leftReturn - rightReturn;
  }
  return right.created_at_utc.localeCompare(left.created_at_utc);
}

function jobLogBody(job: JobRow, raw: boolean): string {
  const text = raw ? (job.log_text ?? "") : filterJobLogText(job.log_text ?? "");
  if (text.trim()) {
    return text;
  }
  if (isActiveJob(job)) {
    return "Waiting for output… (live refresh while the job runs)";
  }
  return "No log output was captured for this job.";
}

function logLineCount(text: string): number {
  if (!text) {
    return 0;
  }
  return text.split("\n").length;
}

const STALE_EMPTY_LOG_MS = 4000;

function formatTerminalJobSession(payload: Record<string, unknown>): string {
  const src = String(payload.src ?? "").trim();
  const dst = String(payload.dst ?? "").trim();
  const pair = src && dst ? `${src.toUpperCase()}/${dst.toUpperCase()}` : "—";
  const interval = String(payload.interval ?? "").trim();
  if (!interval) {
    return pair;
  }
  return `${pair} · ${formatResolutionLabel(interval)}`;
}

function formatJobTypeLabel(jobType: string): string {
  switch (jobType) {
    case "terminal-once":
      return "Single check";
    case "terminal-live":
      return "Continuous polling";
    case "terminal-replay":
      return "CSV replay";
    default:
      return jobType;
  }
}

export function JobMonitor({
  activeJobId,
  onSelectJob,
  jobTypeFilter,
  recentJobsTitle = "Recent jobs",
  recentJobsDescription = "Background tasks on the machine running the Lab API.",
  logMode = "default",
  alwaysShowLogPanel = false,
  embedded = false,
  onWatchJob,
  showSessionMetrics = false,
  jobsListLimit = 50,
  jobsPageSize,
}: JobMonitorProps) {
  const queryClient = useQueryClient();
  const detailRef = useRef<HTMLDivElement>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const logPreRef = useRef<HTMLPreElement>(null);
  const [showStaleLogHint, setShowStaleLogHint] = useState(false);
  const [filterNoise, setFilterNoise] = useState(logMode !== "full");
  const [autoScrollLog, setAutoScrollLog] = useState(true);
  const [copyState, setCopyState] = useState<"idle" | "ok" | "error">("idle");
  const [jobsSort, setJobsSort] = useState<JobsSortKey>(() =>
    showSessionMetrics ? "return-desc" : "time-desc",
  );
  const [jobsPage, setJobsPage] = useState(1);
  const lastFocusedJobPageRef = useRef<string | null>(null);

  const fullLog = logMode === "full";
  const jobsPaginationEnabled = jobsPageSize != null && jobsPageSize > 0;
  const sortByReturn = jobsSort === "return-desc" || jobsSort === "return-asc";
  const showLogCard = Boolean(activeJobId) || alwaysShowLogPanel;

  const activeJobQuery = useQuery({
    queryKey: ["job", activeJobId],
    queryFn: () => api.job(activeJobId!),
    enabled: Boolean(activeJobId),
    staleTime: 0,
    refetchInterval: (query) => {
      const job = query.state.data;
      if (!job || job.id !== activeJobId) {
        return false;
      }
      return isActiveJob(job) ? LIVE_JOB_POLL_MS : false;
    },
  });

  const stopMutation = useMutation({
    mutationFn: (jobId: string) => api.stopJob(jobId),
    onSuccess: (data, jobId) => {
      queryClient.setQueryData<JobRow>(["job", jobId], (current) =>
        current && current.id === jobId ? { ...current, status: data.status } : current,
      );
      queryClient.setQueryData<JobRow[]>(["jobs"], (rows) =>
        rows?.map((job) => (job.id === jobId ? { ...job, status: data.status } : job)),
      );
      void queryClient.invalidateQueries({ queryKey: ["job", jobId] });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  const restartMutation = useMutation({
    mutationFn: (job: JobRow) => api.restartJob(job),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      onSelectJob?.(data.id);
      onWatchJob?.(data.id);
      void queryClient.fetchQuery({
        queryKey: ["job", data.id],
        queryFn: () => api.job(data.id),
      });
    },
  });

  const jobsQuery = useQuery({
    queryKey: ["jobs", jobsListLimit],
    queryFn: () => api.jobs(jobsListLimit),
    refetchInterval: () => {
      const tracked = queryClient.getQueryData<JobRow>(["job", activeJobId]);
      if (tracked && tracked.id === activeJobId && isActiveJob(tracked)) {
        return LIVE_JOBS_LIST_POLL_MS;
      }
      const rows = queryClient.getQueryData<JobRow[]>(["jobs"]) ?? [];
      if (rows.some(isActiveJob)) {
        return LIVE_JOBS_LIST_POLL_MS;
      }
      return 15000;
    },
  });

  const filteredJobs = useMemo(() => {
    const rows = jobsQuery.data ?? [];
    if (!jobTypeFilter) {
      return rows;
    }
    return rows.filter((job) => jobTypeFilter.includes(job.job_type));
  }, [jobsQuery.data, jobTypeFilter]);

  const activeJobIds = useMemo(
    () => filteredJobs.filter(isActiveJob).map((job) => job.id),
    [filteredJobs],
  );

  const activeJobDetailQueries = useQueries({
    queries: activeJobIds.map((jobId) => ({
      queryKey: ["job", jobId],
      queryFn: () => api.job(jobId),
      staleTime: 0,
      refetchInterval: LIVE_JOB_POLL_MS,
    })),
  });

  const jobsForDisplay = useMemo(() => {
    const freshById = new Map<string, JobRow>();
    for (const result of activeJobDetailQueries) {
      if (result.data) {
        freshById.set(result.data.id, result.data);
      }
    }
    return filteredJobs.map((job) => freshById.get(job.id) ?? job);
  }, [filteredJobs, activeJobDetailQueries]);

  const jobsTableRows = useMemo(() => {
    return [...jobsForDisplay].sort((left, right) => compareJobsForSort(left, right, jobsSort));
  }, [jobsForDisplay, jobsSort]);

  const jobsPageCount = useMemo(() => {
    if (!jobsPaginationEnabled) {
      return 1;
    }
    return Math.max(1, Math.ceil(jobsTableRows.length / jobsPageSize!));
  }, [jobsPaginationEnabled, jobsPageSize, jobsTableRows.length]);

  const jobsPageClamped = Math.min(Math.max(jobsPage, 1), jobsPageCount);

  const paginatedJobsTableRows = useMemo(() => {
    if (!jobsPaginationEnabled) {
      return jobsTableRows;
    }
    const start = (jobsPageClamped - 1) * jobsPageSize!;
    return jobsTableRows.slice(start, start + jobsPageSize!);
  }, [jobsPaginationEnabled, jobsPageClamped, jobsPageSize, jobsTableRows]);

  useEffect(() => {
    if (jobsPage !== jobsPageClamped) {
      setJobsPage(jobsPageClamped);
    }
  }, [jobsPage, jobsPageClamped]);

  useEffect(() => {
    setJobsPage(1);
  }, [jobsSort, jobTypeFilter?.join("|")]);

  useEffect(() => {
    if (!jobsPaginationEnabled || !activeJobId) {
      return;
    }
    if (lastFocusedJobPageRef.current === activeJobId) {
      return;
    }
    lastFocusedJobPageRef.current = activeJobId;
    const index = jobsTableRows.findIndex((job) => job.id === activeJobId);
    if (index < 0) {
      return;
    }
    setJobsPage(Math.floor(index / jobsPageSize!) + 1);
  }, [activeJobId, jobsPaginationEnabled, jobsPageSize, jobsTableRows]);

  useEffect(() => {
    const finished = activeJobDetailQueries
      .map((result) => result.data)
      .filter((job): job is JobRow => Boolean(job && !isActiveJob(job)));
    if (finished.length === 0) {
      return;
    }
    queryClient.setQueryData<JobRow[]>(["jobs"], (rows) => {
      if (!rows) {
        return rows;
      }
      const finishedById = new Map(finished.map((job) => [job.id, job]));
      return rows.map((job) => finishedById.get(job.id) ?? job);
    });
  }, [activeJobDetailQueries, queryClient]);

  useEffect(() => {
    const status = activeJobQuery.data?.status;
    if (status === "completed") {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      queryClient.invalidateQueries({ queryKey: ["compares"] });
      queryClient.invalidateQueries({ queryKey: ["sweeps"] });
      queryClient.invalidateQueries({ queryKey: ["experiments"] });
      queryClient.invalidateQueries({ queryKey: ["experiment-artifacts"] });
      queryClient.invalidateQueries({ queryKey: ["stats"] });
      queryClient.invalidateQueries({ queryKey: ["data-csv"] });
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      queryClient.invalidateQueries({ queryKey: ["configs"] });
    }
  }, [activeJobQuery.data?.status, activeJobQuery.data?.job_type, queryClient]);

  useEffect(() => {
    if (activeJobId && detailRef.current) {
      detailRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [activeJobId]);

  const displayJob =
    activeJobQuery.data?.id === activeJobId ? activeJobQuery.data : undefined;

  useEffect(() => {
    setShowStaleLogHint(false);
  }, [activeJobId]);

  useEffect(() => {
    if (!displayJob || !isActiveJob(displayJob) || displayJob.log_text?.trim()) {
      setShowStaleLogHint(false);
      return;
    }
    const timer = window.setTimeout(() => setShowStaleLogHint(true), STALE_EMPTY_LOG_MS);
    return () => window.clearTimeout(timer);
  }, [displayJob?.id, displayJob?.status, displayJob?.log_text]);

  useEffect(() => {
    if (!autoScrollLog || !displayJob || !isActiveJob(displayJob)) {
      return;
    }
    const container = logPreRef.current;
    if (container) {
      container.scrollTop = container.scrollHeight;
    } else {
      logEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [displayJob?.log_text, displayJob?.status, displayJob?.id, autoScrollLog]);

  useEffect(() => {
    setCopyState("idle");
  }, [activeJobId, displayJob?.log_text]);

  const displayedLogText =
    displayJob != null
      ? jobLogBody(displayJob, fullLog && !filterNoise)
      : fullLog
        ? "Start a session above to stream the full terminal output here (signals, errors, and status lines)."
        : "";

  const liveLogPhaseSummary = useMemo(() => {
    if (!displayJob?.log_text?.trim()) {
      return null;
    }
    if (
      displayJob.job_type !== "terminal-once" &&
      displayJob.job_type !== "terminal-live" &&
      displayJob.job_type !== "terminal-replay"
    ) {
      return null;
    }
    return formatLiveLogPhaseSummary(summarizeLiveJobLog(displayJob.log_text));
  }, [displayJob?.job_type, displayJob?.log_text]);

  const discoveryErrorLog = useMemo(() => {
    if (displayJob?.job_type !== "opportunity-discovery" || !displayJob.log_text?.trim()) {
      return "";
    }
    const lines = extractDiscoveryErrorLogLines(displayJob.log_text);
    return lines.length > 0 ? lines.join("\n") : "";
  }, [displayJob?.job_type, displayJob?.log_text]);

  async function copyLogToClipboard() {
    if (!displayedLogText.trim()) {
      return;
    }
    try {
      await navigator.clipboard.writeText(displayedLogText);
      setCopyState("ok");
    } catch {
      setCopyState("error");
    }
  }

  function downloadLogFile() {
    if (!displayedLogText.trim() || !displayJob) {
      return;
    }
    const blob = new Blob([displayedLogText], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `traderbot-${displayJob.job_type}-${displayJob.id.slice(0, 8)}.log`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function viewLog(jobId: string) {
    onSelectJob?.(jobId);
    onWatchJob?.(jobId);
    void queryClient.fetchQuery({
      queryKey: ["job", jobId],
      queryFn: () => api.job(jobId),
    });
  }

  const logTitle =
    displayJob && isActiveJob(displayJob) ? (
      <span className="inline-flex items-center gap-2">
        {fullLog ? "Full session log" : "Job log"}
        <span className="rounded bg-emerald-900/50 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-emerald-200">
          Streaming
        </span>
      </span>
    ) : fullLog ? (
      "Full session log"
    ) : (
      "Job log"
    );

  const logActions =
    displayJob && displayedLogText.trim() ? (
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="secondary" className="text-xs" onClick={() => copyLogToClipboard()}>
          {copyState === "ok" ? "Copied" : copyState === "error" ? "Copy failed" : "Copy log"}
        </Button>
        <Button type="button" variant="ghost" className="text-xs" onClick={() => downloadLogFile()}>
          Download
        </Button>
      </div>
    ) : undefined;

  const logPanelBody = (
    <>
            {activeJobId && activeJobQuery.isPending && !displayJob && (
              <TableSkeleton rows={3} />
            )}
            {activeJobId && activeJobQuery.isError && !displayJob && (
              <ErrorState
                title="Could not load this job"
                error="It may have been cleared from the Lab API database."
              />
            )}
            {(displayJob || (fullLog && alwaysShowLogPanel && !activeJobId)) && (
              <div className="space-y-2 text-sm">
                {displayJob && (
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-muted">{displayJob.id}</span>
                  <StatusBadge status={displayJob.status} />
                  <span className="text-muted">{formatJobTypeLabel(displayJob.job_type)}</span>
                  <div className="ml-auto flex flex-wrap items-center gap-2">
                    {isActiveJob(displayJob) && (
                      <Button
                        type="button"
                        variant="secondary"
                        className="border-red-500/40 text-red-200 hover:border-red-400/70"
                        disabled={stopMutation.isPending}
                        onClick={() => stopMutation.mutate(displayJob.id)}
                      >
                        {stopMutation.isPending ? "Stopping…" : "Stop"}
                      </Button>
                    )}
                    {canRestartJob(displayJob) && (
                      <Button
                        type="button"
                        variant="secondary"
                        className="text-xs"
                        disabled={restartMutation.isPending}
                        onClick={() => restartMutation.mutate(displayJob)}
                      >
                        {restartMutation.isPending ? "Restarting…" : "Restart"}
                      </Button>
                    )}
                  </div>
                </div>
                )}
                {displayJob && stopMutation.isError && (
<ErrorState title="Could not stop this job" error={stopMutation.error} />
                )}
                {displayJob && restartMutation.isError && (
                  <ErrorState title="Could not restart this job" error={restartMutation.error} />
                )}
                {displayJob?.status === "completed" && displayJob.job_type === "strategy-test" && (
                  <p className="text-sm text-emerald-300/90">
                    Strategy test finished — open{" "}
                    <a href="/runs" className="text-accent hover:underline">
                      Runs
                    </a>{" "}
                    for the summary and charts.
                  </p>
                )}
                {displayJob?.status === "completed" && displayJob.job_type === "strategy-compare" && (
                  <p className="text-sm text-emerald-300/90">
                    Compare finished — open{" "}
                    <a href="/runs" className="text-accent hover:underline">
                      Runs
                    </a>{" "}
                    for per-strategy summaries (enable visualize on the next run if charts are empty).
                  </p>
                )}
                {displayJob?.status === "completed" && displayJob.job_type === "strategy-sweep" && (
                  <p className="text-sm text-emerald-300/90">
                    Sweep finished — open{" "}
                    <a href="/runs" className="text-accent hover:underline">
                      Runs
                    </a>{" "}
                    for the winning backtest and parameters.
                  </p>
                )}
                {displayJob?.status === "completed" &&
                  displayJob &&
                  (displayJob.job_type === "terminal-once" ||
                    displayJob.job_type === "terminal-live" ||
                    displayJob.job_type === "terminal-replay") && (
                  <p className="text-sm text-emerald-300/90">
                    Terminal job finished — signal JSON is in the log above. For another run, adjust
                    settings in{" "}
                    <a href="/live" className="text-accent hover:underline">Live trading</a>.
                  </p>
                )}
                {displayJob?.status === "failed" && (
                  <p className="text-sm text-red-400">
                    Job failed — see output below. Fix the issue and retry from{" "}
                    {jobTypeFilter ? (
                      <a href="/live" className="text-accent hover:underline">Live trading</a>
                    ) : (
                      <>
                        <a href="/data" className="text-accent hover:underline">Data</a> or{" "}
                        <a href="/custom" className="text-accent hover:underline">Research</a>
                      </>
                    )}
                    .
                  </p>
                )}
                {liveLogPhaseSummary && (
                  <p className="rounded-lg border border-border bg-surface/70 px-3 py-2 text-xs leading-relaxed text-slate-300">
                    <span className="font-medium text-slate-200">Session trace: </span>
                    {liveLogPhaseSummary}
                  </p>
                )}
                {discoveryErrorLog && (
                  <div className="space-y-1">
                    <p className="text-xs font-medium text-red-300/90">Discovery errors</p>
                    <pre
                      className="max-h-48 overflow-auto rounded-lg border border-red-900/60 bg-red-950/30 p-3 text-xs whitespace-pre-wrap font-mono text-red-100/95"
                    >
                      {discoveryErrorLog}
                    </pre>
                  </div>
                )}
                {displayJob && showStaleLogHint && (
                  <p className="text-sm text-amber-200/90">
                    No log lines yet. If this stays empty, the Lab API may have restarted while an
                    older job was still marked running — run compare again from{" "}
                    <a href="/custom" className="text-accent hover:underline">Research</a> (or
                    restart with <code className="text-xs">./run-lab-api.sh</code> and start a new
                    job).
                  </p>
                )}
                {fullLog && (
                  <div className="flex flex-wrap items-center gap-4 text-xs text-muted">
                    <label className="flex cursor-pointer items-center gap-2 text-slate-300">
                      <input
                        type="checkbox"
                        checked={autoScrollLog}
                        onChange={(event) => setAutoScrollLog(event.target.checked)}
                      />
                      Auto-scroll while running
                    </label>
                    <label className="flex cursor-pointer items-center gap-2 text-slate-300">
                      <input
                        type="checkbox"
                        checked={filterNoise}
                        onChange={(event) => setFilterNoise(event.target.checked)}
                      />
                      Hide Lab API HTTP lines
                    </label>
                    {displayJob?.log_text && (
                      <span>
                        {logLineCount(displayJob.log_text)} lines ·{" "}
                        {displayJob.log_text.length.toLocaleString()} characters
                      </span>
                    )}
                  </div>
                )}
                <pre
                  ref={logPreRef}
                  className={`overflow-auto rounded-lg border border-border bg-surface p-3 text-xs whitespace-pre-wrap font-mono ${
                    fullLog ? "min-h-[28rem] max-h-[min(75vh,960px)]" : "max-h-80"
                  } ${displayJob?.log_text?.trim() || (fullLog && !activeJobId) ? "text-slate-200" : "text-muted"}`}
                >
                  {displayedLogText}
                  <div ref={logEndRef} />
                </pre>
              </div>
            )}
    </>
  );

  const jobsTableBody = (
    <>
      {jobsTableRows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="data">
            <thead>
              <tr>
                {showSessionMetrics && sortByReturn && <th className="text-left">Rank</th>}
                <th>Type</th>
                <th>Session</th>
                {showSessionMetrics && (
                  <>
                    <th>Strategy</th>
                    <th className="text-right">Return</th>
                    <th className="text-right">Equity</th>
                    <th className="text-right">Rounds</th>
                  </>
                )}
                <th>Status</th>
                <th>Created</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {paginatedJobsTableRows.map((job, rowIndex) => {
                const selected = activeJobId === job.id;
                const metrics = showSessionMetrics ? liveSessionMetricsFromJob(job) : null;
                const strategyId =
                  typeof job.payload?.strategy === "string" ? job.payload.strategy : "—";
                const isLiveOrder = Boolean(job.payload?.live);
                const globalRowIndex = jobsPaginationEnabled
                  ? (jobsPageClamped - 1) * jobsPageSize! + rowIndex
                  : rowIndex;
                const paperRank = jobsTableRows
                  .slice(0, globalRowIndex)
                  .filter((row) => !row.payload?.live).length;
                return (
                  <tr key={job.id} className={selected ? "bg-accent/10" : undefined}>
                    {showSessionMetrics && sortByReturn && (
                      <td className="text-muted tabular-nums">
                        {isLiveOrder ? "—" : `#${paperRank + 1}`}
                      </td>
                    )}
                    <td>{formatJobTypeLabel(job.job_type)}</td>
                    <td className="text-xs text-muted">
                      {job.job_type.startsWith("terminal-")
                        ? formatTerminalJobSession(job.payload ?? {})
                        : "—"}
                    </td>
                    {showSessionMetrics && (
                      <>
                        <td className="font-mono text-xs text-muted">{strategyId}</td>
                        <td
                          className={`text-right tabular-nums text-xs ${
                            isLiveOrder
                              ? "text-muted"
                              : (metrics?.sessionReturnPct ?? 0) >= 0
                                ? "text-emerald-300"
                                : "text-red-300"
                          }`}
                        >
                          {isLiveOrder
                            ? "—"
                            : metrics?.sessionReturnPct != null
                              ? `${metrics.sessionReturnPct >= 0 ? "+" : ""}${metrics.sessionReturnPct.toFixed(2)}%`
                              : "—"}
                        </td>
                        <td className="text-right tabular-nums text-xs text-slate-200">
                          {metrics?.currentEquity != null ? formatMoney(metrics.currentEquity) : "—"}
                        </td>
                        <td className="text-right tabular-nums text-xs text-muted">
                          {metrics != null
                            ? metrics.openBuyLegs > 0
                              ? `${metrics.roundTripCount}+${metrics.openBuyLegs}`
                              : String(metrics.roundTripCount)
                            : "—"}
                        </td>
                      </>
                    )}
                    <td><StatusBadge status={job.status} /></td>
                    <td className="text-xs text-muted">{formatUtcTimestamp(job.created_at_utc)}</td>
                    <td className="space-x-2 text-right">
                      {isActiveJob(job) && (
                        <button
                          type="button"
                          className="text-xs text-red-300 hover:underline"
                          disabled={stopMutation.isPending}
                          onClick={() => stopMutation.mutate(job.id)}
                        >
                          Stop
                        </button>
                      )}
                      {canRestartJob(job) && (
                        <button
                          type="button"
                          className="text-xs text-slate-200 hover:underline"
                          disabled={restartMutation.isPending}
                          onClick={() => restartMutation.mutate(job)}
                        >
                          Restart
                        </button>
                      )}
                      {onSelectJob && (
                        <button
                          type="button"
                          className="text-xs text-accent hover:underline"
                          onClick={() => viewLog(job.id)}
                        >
                          {selected ? "Selected" : "Select"}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {jobsPaginationEnabled && jobsTableRows.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
          <span>
            {(jobsPageClamped - 1) * jobsPageSize! + 1}–
            {Math.min(jobsPageClamped * jobsPageSize!, jobsTableRows.length)} of {jobsTableRows.length}{" "}
            jobs
          </span>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="secondary"
              className="text-xs"
              disabled={jobsPageClamped <= 1}
              onClick={() => setJobsPage((page) => Math.max(1, page - 1))}
            >
              Previous
            </Button>
            <span className="tabular-nums text-slate-300">
              Page {jobsPageClamped} / {jobsPageCount}
            </span>
            <Button
              type="button"
              variant="secondary"
              className="text-xs"
              disabled={jobsPageClamped >= jobsPageCount}
              onClick={() => setJobsPage((page) => Math.min(jobsPageCount, page + 1))}
            >
              Next
            </Button>
          </div>
        </div>
      )}
      {jobsQuery.isLoading && <TableSkeleton rows={4} />}
      {jobsQuery.isError && <ErrorState title="Failed to load jobs" error={jobsQuery.error} />}
      {jobsQuery.isSuccess && jobsTableRows.length === 0 && (
        <EmptyState
          title={jobTypeFilter ? "No trading jobs yet" : "No background jobs yet"}
          description={
            jobTypeFilter
              ? "Start a paper or live session above."
              : "Jobs you start appear here with live status and logs."
          }
        />
      )}
    </>
  );

  const jobsSortControl = (
    <label className="flex items-center gap-2 text-xs text-muted">
      <span className="text-slate-300">Sort</span>
      <select
        value={jobsSort}
        onChange={(event) => setJobsSort(event.target.value as JobsSortKey)}
        className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-slate-200"
      >
        {showSessionMetrics && (
          <>
            <option value="return-desc">Return (best first)</option>
            <option value="return-asc">Return (worst first)</option>
          </>
        )}
        <option value="time-desc">Time (newest first)</option>
        <option value="time-asc">Time (oldest first)</option>
      </select>
    </label>
  );

  const jobsSection = embedded ? (
    <section className="border-b border-border pb-6">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="text-sm font-medium text-white">{recentJobsTitle}</h3>
          <p className="mt-1 text-xs leading-relaxed text-muted">{recentJobsDescription}</p>
        </div>
        {jobsSortControl}
      </div>
      {jobsTableBody}
    </section>
  ) : (
    <Card
      title={recentJobsTitle}
      description={recentJobsDescription}
      actions={jobsSortControl}
    >
      {jobsTableBody}
    </Card>
  );

  const logSection =
    showLogCard &&
    (embedded ? (
      <section ref={detailRef} className="border-b border-border py-6">
        <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 className="text-sm font-medium text-white">{logTitle}</h3>
            {fullLog && (
              <p className="mt-1 text-xs text-muted">
                Complete stdout/stderr from the terminal job. Refreshes every 500ms while the job runs.
              </p>
            )}
          </div>
          {logActions}
        </div>
        {logPanelBody}
      </section>
    ) : (
      <div ref={detailRef}>
        <Card
          title={logTitle}
          description={
            fullLog
              ? "Complete stdout/stderr from the terminal job. Refreshes every 500ms while the job runs."
              : undefined
          }
          actions={logActions}
        >
          {logPanelBody}
        </Card>
      </div>
    ));

  return (
    <div className={embedded ? "space-y-0" : "space-y-4"}>
      {embedded ? (
        <>
          {jobsSection}
          {logSection}
        </>
      ) : (
        <>
          {logSection}
          {jobsSection}
        </>
      )}
    </div>
  );
}
