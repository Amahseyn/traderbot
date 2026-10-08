"use client";

import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type JobRow } from "@/lib/api";
import { formatResolutionLabel, formatUtcTimestamp } from "@/lib/format";
import { filterJobLogText } from "@/lib/jobLog";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/StatusBadge";

const LIVE_JOB_POLL_MS = 500;
const LIVE_JOBS_LIST_POLL_MS = 1000;

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
};

function isActiveJob(job: JobRow): boolean {
  return job.status === "queued" || job.status === "running";
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
}: JobMonitorProps) {
  const queryClient = useQueryClient();
  const detailRef = useRef<HTMLDivElement>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const logPreRef = useRef<HTMLPreElement>(null);
  const [showStaleLogHint, setShowStaleLogHint] = useState(false);
  const [filterNoise, setFilterNoise] = useState(logMode !== "full");
  const [autoScrollLog, setAutoScrollLog] = useState(true);
  const [copyState, setCopyState] = useState<"idle" | "ok" | "error">("idle");

  const fullLog = logMode === "full";
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

  const jobsQuery = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api.jobs(),
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
    void queryClient.fetchQuery({
      queryKey: ["job", jobId],
      queryFn: () => api.job(jobId),
    });
  }

  return (
    <div className="space-y-4">
      {showLogCard && (
        <div ref={detailRef}>
          <Card
            title={
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
              )
            }
            description={
              fullLog
                ? "Complete stdout/stderr from the terminal job. Refreshes every 500ms while the job runs."
                : undefined
            }
            actions={
              displayJob && displayedLogText.trim() ? (
                <div className="flex flex-wrap items-center gap-2">
                  <Button type="button" variant="secondary" className="text-xs" onClick={() => copyLogToClipboard()}>
                    {copyState === "ok" ? "Copied" : copyState === "error" ? "Copy failed" : "Copy log"}
                  </Button>
                  <Button type="button" variant="ghost" className="text-xs" onClick={() => downloadLogFile()}>
                    Download
                  </Button>
                </div>
              ) : undefined
            }
          >
            {activeJobId && activeJobQuery.isPending && !displayJob && (
              <p className="text-sm text-muted">Loading job {activeJobId.slice(0, 8)}…</p>
            )}
            {activeJobId && activeJobQuery.isError && !displayJob && (
              <p className="text-sm text-red-400">
                Could not load this job. It may have been cleared from the Lab API database.
              </p>
            )}
            {(displayJob || (fullLog && alwaysShowLogPanel && !activeJobId)) && (
              <div className="space-y-2 text-sm">
                {displayJob && (
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-muted">{displayJob.id}</span>
                  <StatusBadge status={displayJob.status} />
                  <span className="text-muted">{formatJobTypeLabel(displayJob.job_type)}</span>
                  {isActiveJob(displayJob) && (
                    <Button
                      type="button"
                      variant="secondary"
                      className="ml-auto border-red-500/40 text-red-200 hover:border-red-400/70"
                      disabled={stopMutation.isPending}
                      onClick={() => stopMutation.mutate(displayJob.id)}
                    >
                      {stopMutation.isPending ? "Stopping…" : "Stop"}
                    </Button>
                  )}
                </div>
                )}
                {displayJob && stopMutation.isError && (
                  <p className="text-sm text-red-400">
                    {stopMutation.error instanceof Error
                      ? stopMutation.error.message
                      : "Could not stop this job."}
                  </p>
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
                        <a href="/custom" className="text-accent hover:underline">Custom research</a>
                      </>
                    )}
                    .
                  </p>
                )}
                {displayJob && showStaleLogHint && (
                  <p className="text-sm text-amber-200/90">
                    No log lines yet. If this stays empty, the Lab API may have restarted while an
                    older job was still marked running — run compare again from{" "}
                    <a href="/custom" className="text-accent hover:underline">Custom research</a> (or
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
          </Card>
        </div>
      )}

      <Card title={recentJobsTitle} description={recentJobsDescription}>
        <table className="data">
          <thead>
            <tr>
              <th>Type</th>
              <th>Session</th>
              <th>Status</th>
              <th>Created</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {jobsForDisplay.map((job) => {
              const selected = activeJobId === job.id;
              return (
                <tr key={job.id} className={selected ? "bg-accent/10" : undefined}>
                  <td>{formatJobTypeLabel(job.job_type)}</td>
                  <td className="text-xs text-muted">
                    {job.job_type.startsWith("terminal-")
                      ? formatTerminalJobSession(job.payload ?? {})
                      : "—"}
                  </td>
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
                    {onSelectJob && (
                      <button
                        type="button"
                        className="text-xs text-accent hover:underline"
                        onClick={() => viewLog(job.id)}
                      >
                        {selected ? "Viewing log" : "View log"}
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {jobsQuery.isLoading && <p className="text-muted mt-2 text-sm">Loading jobs…</p>}
        {!jobsQuery.isLoading && jobsForDisplay.length === 0 && (
          <p className="text-muted mt-2 text-sm">
            {jobTypeFilter ? "No trading jobs yet." : "No background jobs yet."}
          </p>
        )}
      </Card>
    </div>
  );
}
