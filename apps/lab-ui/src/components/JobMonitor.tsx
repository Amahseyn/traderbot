"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, type JobRow } from "@/lib/api";
import { formatUtcTimestamp } from "@/lib/format";
import { filterJobLogText } from "@/lib/jobLog";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/StatusBadge";

const LIVE_JOB_POLL_MS = 500;
const LIVE_JOBS_LIST_POLL_MS = 1000;

type JobMonitorProps = {
  activeJobId: string | null;
  onSelectJob?: (jobId: string) => void;
};

function isActiveJob(job: JobRow): boolean {
  return job.status === "queued" || job.status === "running";
}

function jobLogBody(job: JobRow): string {
  const text = filterJobLogText(job.log_text ?? "");
  if (text.trim()) {
    return text;
  }
  if (isActiveJob(job)) {
    return "Waiting for output… (live refresh while the job runs)";
  }
  return "No log output was captured for this job.";
}

const STALE_EMPTY_LOG_MS = 4000;

export function JobMonitor({ activeJobId, onSelectJob }: JobMonitorProps) {
  const queryClient = useQueryClient();
  const detailRef = useRef<HTMLDivElement>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const [showStaleLogHint, setShowStaleLogHint] = useState(false);

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
    if (displayJob && isActiveJob(displayJob)) {
      logEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [displayJob?.log_text, displayJob?.status, displayJob?.id]);

  function viewLog(jobId: string) {
    onSelectJob?.(jobId);
    void queryClient.fetchQuery({
      queryKey: ["job", jobId],
      queryFn: () => api.job(jobId),
    });
  }

  return (
    <div className="space-y-4">
      {activeJobId && (
        <div ref={detailRef}>
          <Card
            title={
              displayJob && isActiveJob(displayJob) ? (
                <span className="inline-flex items-center gap-2">
                  Job log
                  <span className="rounded bg-emerald-900/50 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-emerald-200">
                    Live
                  </span>
                </span>
              ) : (
                "Job log"
              )
            }
          >
            {activeJobQuery.isPending && !displayJob && (
              <p className="text-sm text-muted">Loading job {activeJobId.slice(0, 8)}…</p>
            )}
            {activeJobQuery.isError && !displayJob && (
              <p className="text-sm text-red-400">
                Could not load this job. It may have been cleared from the Lab API database.
              </p>
            )}
            {displayJob && (
              <div className="space-y-2 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-muted">{displayJob.id}</span>
                  <StatusBadge status={displayJob.status} />
                  <span className="text-muted">{displayJob.job_type}</span>
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
                {stopMutation.isError && (
                  <p className="text-sm text-red-400">
                    {stopMutation.error instanceof Error
                      ? stopMutation.error.message
                      : "Could not stop this job."}
                  </p>
                )}
                {displayJob.status === "completed" && displayJob.job_type === "strategy-test" && (
                  <p className="text-sm text-emerald-300/90">
                    Strategy test finished — open{" "}
                    <a href="/runs" className="text-accent hover:underline">
                      Runs
                    </a>{" "}
                    for the summary and charts.
                  </p>
                )}
                {displayJob.status === "completed" && displayJob.job_type === "strategy-compare" && (
                  <p className="text-sm text-emerald-300/90">
                    Compare finished — open{" "}
                    <a href="/runs" className="text-accent hover:underline">
                      Runs
                    </a>{" "}
                    for per-strategy summaries (enable visualize on the next run if charts are empty).
                  </p>
                )}
                {displayJob.status === "completed" && displayJob.job_type === "strategy-sweep" && (
                  <p className="text-sm text-emerald-300/90">
                    Sweep finished — open{" "}
                    <a href="/runs" className="text-accent hover:underline">
                      Runs
                    </a>{" "}
                    for the winning backtest and parameters.
                  </p>
                )}
                {displayJob.status === "failed" && (
                  <p className="text-sm text-red-400">
                    Job failed — see output below. Fix the issue and retry from{" "}
                    <a href="/data" className="text-accent hover:underline">Data</a> or{" "}
                    <a href="/custom" className="text-accent hover:underline">Custom research</a>.
                  </p>
                )}
                {showStaleLogHint && (
                  <p className="text-sm text-amber-200/90">
                    No log lines yet. If this stays empty, the Lab API may have restarted while an
                    older job was still marked running — run compare again from{" "}
                    <a href="/custom" className="text-accent hover:underline">Custom research</a> (or
                    restart with <code className="text-xs">./run-lab-api.sh</code> and start a new
                    job).
                  </p>
                )}
                <pre
                  className={`max-h-80 overflow-auto rounded-lg border border-border bg-surface p-3 text-xs whitespace-pre-wrap font-mono ${
                    displayJob.log_text?.trim() ? "text-slate-200" : "text-muted"
                  }`}
                >
                  {jobLogBody(displayJob)}
                  <div ref={logEndRef} />
                </pre>
              </div>
            )}
          </Card>
        </div>
      )}

      <Card title="Recent jobs" description="Background tasks on the machine running the Lab API.">
        <table className="data">
          <thead>
            <tr>
              <th>Type</th>
              <th>Status</th>
              <th>Created</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {(jobsQuery.data ?? []).map((job) => {
              const selected = activeJobId === job.id;
              return (
                <tr key={job.id} className={selected ? "bg-accent/10" : undefined}>
                  <td>{job.job_type}</td>
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
        {!jobsQuery.isLoading && (jobsQuery.data ?? []).length === 0 && (
          <p className="text-muted mt-2 text-sm">No background jobs yet.</p>
        )}
      </Card>
    </div>
  );
}
