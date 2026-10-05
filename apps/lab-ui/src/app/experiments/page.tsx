"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { ArtifactGallery } from "@/components/ArtifactGallery";
import { JobForms } from "@/components/JobForms";
import { JobMonitor } from "@/components/JobMonitor";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { api } from "@/lib/api";
import { formatUtcTimestamp } from "@/lib/format";
import { PipelineRunCard } from "@/components/PipelineRunCard";
import { PipelineLibrary } from "@/components/PipelineLibrary";
import { HORIZON_OPTIONS, catalogPipelines, groupPipelineList, pipelineLabel } from "@/lib/pipelines";
import { loadPipelineLibrary, savePipelineLibrary, type PipelineLibraryState } from "@/lib/pipelineLibrary";
import type { CompareSession, ExperimentRow, PipelineSpecRow } from "@/lib/api";

function PipelineBlock({
  pipeline,
  experiments,
  running,
  runError,
  runningExperimentId,
  titleOverride,
  onRunPipeline,
  onRunExperiment,
}: {
  pipeline: PipelineSpecRow;
  experiments: ExperimentRow[];
  running: boolean;
  runError?: string | null;
  runningExperimentId: string | null;
  titleOverride?: string;
  onRunPipeline: (body: Record<string, unknown>) => void;
  onRunExperiment: (experimentId: string, body: ExperimentRunBody) => void;
}) {
  const label = pipelineLabel(pipeline);
  const title = titleOverride?.trim() || label.title;
  return (
    <div className="border-t border-border pt-4">
      <PipelineRunCard
        pipeline={pipeline}
        running={running}
        error={runError}
        titleOverride={title}
        onRun={onRunPipeline}
      />
      {experiments.length === 0 ? null : (
        <div className="mt-3 space-y-3">
          {experiments.map((row) => (
            <ExperimentCard
              key={row.experiment_id}
              experiment={row}
              pipelineTitle={title}
              running={runningExperimentId === row.experiment_id}
              onRun={(body) => onRunExperiment(row.experiment_id, body)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function CompareSessionCard({ session }: { session: CompareSession }) {
  const [open, setOpen] = useState(false);

  return (
    <Card className="!p-4">
      <button
        type="button"
        className="flex w-full items-start justify-between gap-4 text-left"
        onClick={() => setOpen((value) => !value)}
      >
        <div className="min-w-0 space-y-1">
          <div className="text-sm text-white">{session.dataset_label ?? "Dataset"}</div>
          <div className="text-sm">
            Best: <span className="text-white">{session.best_strategy_id ?? "—"}</span>
            <span className="text-muted"> · {session.bar_count ?? "—"} bars</span>
            {typeof session.summary.mode === "string" && (
              <span className="text-muted">
                {" "}
                · {session.summary.mode === "ml" ? "ML results" : "Strategies"}
              </span>
            )}
          </div>
          <div className="text-xs text-muted">{formatUtcTimestamp(session.created_at_utc)}</div>
        </div>
        <span className="text-muted text-sm">{open ? "▲" : "▼"}</span>
      </button>
      {open && session.artifacts.length > 0 && (
        <div className="mt-4 border-t border-border pt-4">
          <ArtifactGallery artifacts={session.artifacts} title="Compare charts" />
        </div>
      )}
      {open && session.artifacts.length === 0 && (
        <p className="text-muted mt-4 border-t border-border pt-4 text-sm">
          No charts stored for this session. Re-run compare with visualize enabled.
        </p>
      )}
    </Card>
  );
}

function ExperimentSteps({ experiment }: { experiment: ExperimentRow }) {
  const testSteps = experiment.payload.test_steps;
  if (!Array.isArray(testSteps) || testSteps.length === 0) {
    return null;
  }
  return (
    <div className="mt-3 border-t border-border pt-3">
      <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Test steps</h4>
      <table className="data text-xs">
        <thead>
          <tr>
            <th>Step</th>
            <th>Title</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {testSteps.map((step) => {
            if (!step || typeof step !== "object") return null;
            const record = step as Record<string, unknown>;
            return (
              <tr key={String(record.step_id ?? record.title)}>
                <td className="font-mono">{String(record.step_id ?? "—")}</td>
                <td>{String(record.title ?? "—")}</td>
                <td>
                  <StatusBadge status={String(record.status ?? "unknown")} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

type ExperimentRunBody = {
  params: Record<string, unknown>;
  step_params: Record<string, Record<string, unknown>>;
};

const PARAM_LABELS: Record<string, string> = {
  horizon: "Horizon",
  all_assets: "Every file",
  symbol: "Symbol",
  window_hours: "Holdout window",
  initial_cash: "Starting cash",
  train_ratio: "Training share",
  fast: "Fast window",
  slow: "Slow window",
  tail_bars: "Last bars",
  holdout_tail_bars: "Holdout bars",
};

const PARAM_ORDER = Object.keys(PARAM_LABELS);

const HORIZON_PIPELINES = new Set(["crypto-1h-local"]);

const DEFAULT_HORIZON: Record<string, string> = {
  "crypto-1h-local": "1h",
};

const WINDOW_OPTIONS = [
  { value: "", label: "Entire file" },
  { value: "24", label: "Last 24 hours" },
  { value: "60", label: "Last 60 hours" },
  { value: "168", label: "Last 7 days" },
];

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return { ...(value as Record<string, unknown>) };
}

function orderedParamKeys(record: Record<string, unknown>): string[] {
  const keys = Object.keys(record);
  const visible = keys.filter((key) => key !== "holdout_tail_bars" || !keys.includes("window_hours"));
  return [...PARAM_ORDER.filter((key) => visible.includes(key)), ...visible.filter((key) => !PARAM_ORDER.includes(key)).sort()];
}

function ParamFields({
  values,
  onChange,
}: {
  values: Record<string, unknown>;
  onChange: (key: string, value: unknown) => void;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {orderedParamKeys(values).map((key) => {
        const value = values[key];
        const label = PARAM_LABELS[key] ?? key.replaceAll("_", " ");
        if (typeof value === "boolean" || key === "all_assets") {
          return (
            <label key={key} className="flex items-center gap-2 text-sm text-slate-200">
              <input
                type="checkbox"
                checked={Boolean(value)}
                onChange={(event) => onChange(key, event.target.checked)}
              />
              {label}
            </label>
          );
        }
        if (key === "horizon" || key === "window_hours") {
          const options =
            key === "horizon" ? HORIZON_OPTIONS : WINDOW_OPTIONS;
          const current = value == null || value === "" ? "" : String(value);
          const choices = options.some((option) => option.value === current)
            ? options
            : [...options, { value: current, label: current }];
          return (
            <Field key={key} label={label}>
              <SelectInput value={current} onChange={(event) => {
                const next = event.target.value;
                onChange(key, key === "window_hours" ? (next === "" ? null : Number(next)) : next);
              }}>
                {choices.map((option) => (
                  <option key={option.value || "empty"} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </SelectInput>
            </Field>
          );
        }
        if (typeof value === "number" || value == null) {
          return (
            <Field key={key} label={label}>
              <TextInput
                type="number"
                value={value == null ? "" : String(value)}
                onChange={(event) => {
                  const next = event.target.value;
                  onChange(key, next === "" ? null : Number(next));
                }}
              />
            </Field>
          );
        }
        return (
          <Field key={key} label={label}>
            <TextInput value={String(value)} onChange={(event) => onChange(key, event.target.value)} />
          </Field>
        );
      })}
    </div>
  );
}

function ExperimentCard({
  experiment,
  pipelineTitle,
  onRun,
  running,
}: {
  experiment: ExperimentRow;
  pipelineTitle?: string;
  onRun: (body: ExperimentRunBody) => void;
  running: boolean;
}) {
  const [params, setParams] = useState(() => {
    const initial = asRecord(experiment.payload.params);
    if (!("horizon" in initial) && experiment.pipeline_id && HORIZON_PIPELINES.has(experiment.pipeline_id)) {
      initial.horizon = DEFAULT_HORIZON[experiment.pipeline_id] ?? "usual";
    }
    return initial;
  });
  const [stepParams, setStepParams] = useState<Record<string, Record<string, unknown>>>(() => {
    const steps = experiment.payload.test_steps;
    const initial: Record<string, Record<string, unknown>> = {};
    if (!Array.isArray(steps)) return initial;
    for (const step of steps) {
      if (!step || typeof step !== "object") continue;
      const record = step as Record<string, unknown>;
      const stepId = String(record.step_id ?? "");
      if (!stepId) continue;
      initial[stepId] = asRecord(record.params);
    }
    return initial;
  });
  const chartsQuery = useQuery({
    queryKey: ["experiment-artifacts", experiment.experiment_id],
    queryFn: () => api.experimentArtifacts(experiment.experiment_id),
    enabled: Boolean(experiment.experiment_id),
  });

  return (
    <Card className="!p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-medium text-white">{experiment.title ?? experiment.experiment_id}</div>
          <div className="font-mono text-xs text-muted">{experiment.experiment_id}</div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
            <StatusBadge status={experiment.status ?? "unknown"} />
            {experiment.pipeline_id && (
              <span className="text-muted">
                {pipelineTitle ?? experiment.pipeline_id}
                <span className="font-mono text-xs"> ({experiment.pipeline_id})</span>
              </span>
            )}
            {(experiment.test_step_count ?? 0) > 0 && (
              <span className="text-muted text-xs">{experiment.test_step_count} steps</span>
            )}
          </div>
          {experiment.last_error && (
            <p className="mt-2 text-xs text-red-400">{experiment.last_error}</p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {experiment.runnable && (
            <Button
              variant="secondary"
              disabled={running}
              onClick={() => onRun({ params, step_params: stepParams })}
            >
              {running ? "Starting…" : "Run pipeline"}
            </Button>
          )}
        </div>
      </div>
      <dl className="mt-3 grid gap-1 text-xs text-muted sm:grid-cols-2">
        <div>
          <dt className="inline">Updated: </dt>
          <dd className="inline">{formatUtcTimestamp(experiment.updated_at_utc)}</dd>
        </div>
        <div>
          <dt className="inline">Runnable: </dt>
          <dd className="inline">{experiment.runnable ? "yes (config on disk)" : "no"}</dd>
        </div>
      </dl>
      {Object.keys(params).length > 0 && (
        <div className="mt-4 border-t border-border pt-4">
          <h4 className="mb-3 text-xs font-medium uppercase tracking-wide text-muted">Settings</h4>
          <ParamFields
            values={params}
            onChange={(key, value) =>
              setParams((current) => ({
                ...current,
                [key]: value,
                ...(key === "window_hours" ? { holdout_tail_bars: value } : {}),
              }))
            }
          />
        </div>
      )}
      <ExperimentSteps experiment={experiment} />
      {Object.entries(stepParams).map(([stepId, values]) =>
        Object.keys(values).length === 0 ? null : (
          <div key={stepId} className="mt-4 border-t border-border pt-4">
            <h4 className="mb-3 text-xs font-medium uppercase tracking-wide text-muted">{stepId}</h4>
            <ParamFields
              values={values}
              onChange={(key, value) =>
                setStepParams((current) => ({
                  ...current,
                  [stepId]: {
                    ...current[stepId],
                    [key]: value,
                    ...(key === "window_hours" ? { holdout_tail_bars: value } : {}),
                  },
                }))
              }
            />
          </div>
        ),
      )}
      {(chartsQuery.data?.artifacts.length ?? 0) > 0 && (
        <div className="mt-4 border-t border-border pt-4">
          <ArtifactGallery artifacts={chartsQuery.data!.artifacts} title="Solution charts" />
        </div>
      )}
    </Card>
  );
}

type LabSection = "run" | "pipelines" | "compares";

const SECTIONS: { id: LabSection; label: string; hint: string }[] = [
  { id: "run", label: "Run", hint: "Test or compare strategies, or run a saved pipeline." },
  { id: "pipelines", label: "Pipelines", hint: "Active pipelines are the ones you can run. The library turns full pipelines on, off, or renames them." },
  { id: "compares", label: "Compare results", hint: "Ranking charts from strategy compare." },
];

export default function ExperimentsPage() {
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const [runningExperimentId, setRunningExperimentId] = useState<string | null>(null);
  const [runningPipelineId, setRunningPipelineId] = useState<string | null>(null);
  const [groupFilter, setGroupFilter] = useState("");
  const [section, setSection] = useState<LabSection>("run");
  const [library, setLibrary] = useState<PipelineLibraryState | null>(null);

  useEffect(() => {
    setLibrary(loadPipelineLibrary());
  }, []);

  useEffect(() => {
    const applyHash = () => {
      const hash = window.location.hash;
      if (hash === "#compares") setSection("compares");
      else if (hash === "#pipelines") setSection("pipelines");
      else setSection("run");
    };
    applyHash();
    window.addEventListener("hashchange", applyHash);
    return () => window.removeEventListener("hashchange", applyHash);
  }, []);

  function openSection(next: LabSection) {
    setSection(next);
    const hash = next === "run" ? "" : `#${next}`;
    window.history.replaceState(null, "", `/experiments${hash}`);
  }

  const pipelinesQuery = useQuery({ queryKey: ["pipelines"], queryFn: api.pipelines });
  const experimentsQuery = useQuery({ queryKey: ["experiments"], queryFn: api.experiments });
  const comparesQuery = useQuery({ queryKey: ["compares"], queryFn: api.compareSessions });

  const syncMutation = useMutation({
    mutationFn: api.syncExperiments,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["experiments"] });
      queryClient.invalidateQueries({ queryKey: ["stats"] });
    },
  });

  const directPipelineMutation = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.postJob("pipeline-run", body),
    onSuccess: (data) => {
      setJobId(data.id);
      setRunningPipelineId(null);
    },
  });

  const pipelineMutation = useMutation({
    mutationFn: (body: { experiment_id: string } & ExperimentRunBody) =>
      api.postJob("pipeline-run-config", body),
    onSuccess: (data) => {
      setJobId(data.id);
      setRunningExperimentId(null);
    },
    onError: () => setRunningExperimentId(null),
  });

  const pipelines = catalogPipelines(pipelinesQuery.data);

  const experiments = experimentsQuery.data ?? [];

  const experimentsByPipeline = useMemo(() => {
    const groups = new Map<string, ExperimentRow[]>();
    for (const row of experiments) {
      const key = row.pipeline_id ?? "unknown";
      const bucket = groups.get(key) ?? [];
      bucket.push(row);
      groups.set(key, bucket);
    }
    return groups;
  }, [experiments]);

  const pipelineGroups = useMemo(() => {
    const known = new Set(pipelines.map((pipeline) => pipeline.id));
    const activeIds = new Set(library?.activeIds ?? []);
    const orphans: PipelineSpecRow[] = [...experimentsByPipeline.keys()]
      .filter((pipelineId) => pipelineId !== "unknown" && !known.has(pipelineId))
      .map((pipelineId) => ({
        id: pipelineId,
        title: pipelineId,
        description: "Experiment catalog references a pipeline id not in the current registry.",
      }));
    const visible = pipelines.filter((pipeline) => activeIds.has(pipeline.id));
    const grouped = groupPipelineList([...visible, ...orphans]);
    if (!groupFilter) return grouped;
    return grouped.filter((entry) => entry.group.id === groupFilter);
  }, [pipelines, experimentsByPipeline, groupFilter, library]);

  const savedCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const [pipelineId, rows] of experimentsByPipeline) {
      counts.set(pipelineId, rows.length);
    }
    return counts;
  }, [experimentsByPipeline]);

  function updateLibrary(next: PipelineLibraryState) {
    setLibrary(next);
    savePipelineLibrary(next);
  }

  const sectionHint = SECTIONS.find((item) => item.id === section)?.hint;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Lab"
        description="Run a strategy or saved pipeline, then watch the job on the right. Compare charts stay on this page. A single test is listed under Runs."
      />

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(20rem,26rem)]">
        <div className="min-w-0 space-y-4">
          <div className="tab-list">
            {SECTIONS.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`tab ${section === item.id ? "tab-active" : ""}`}
                onClick={() => openSection(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
          {sectionHint && <p className="text-sm text-muted">{sectionHint}</p>}

          {section === "run" && <JobForms onJob={setJobId} />}

          {section === "pipelines" && (
            <section className="space-y-8">
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="section-title">
                    Active ({pipelineGroups.reduce((count, entry) => count + entry.pipelines.length, 0)})
                  </h2>
                  <div className="flex flex-wrap items-center gap-2">
                    <select
                      className="rounded-lg border border-border bg-surface px-3 py-1.5 text-sm"
                      value={groupFilter}
                      onChange={(event) => setGroupFilter(event.target.value)}
                      aria-label="Filter active pipelines"
                    >
                      <option value="">Show all</option>
                      {groupPipelineList(pipelines).map((entry) => (
                        <option key={entry.group.id} value={entry.group.id}>
                          {entry.group.title}
                        </option>
                      ))}
                    </select>
                    <Button
                      variant="secondary"
                      disabled={syncMutation.isPending}
                      onClick={() => syncMutation.mutate()}
                    >
                      {syncMutation.isPending ? "Syncing…" : "Sync configs"}
                    </Button>
                  </div>
                </div>
                <p className="text-sm text-muted">
                  These are the pipelines you turned on. Each card runs that job. Saved configs stay under the card.
                </p>
                {syncMutation.isError && (
                  <p className="text-sm text-red-400">
                    {syncMutation.error instanceof Error
                      ? syncMutation.error.message
                      : "Experiment sync failed."}
                  </p>
                )}
                {syncMutation.isSuccess && (
                  <p className="text-sm text-muted">
                    Registered {syncMutation.data.registered_count} experiment config
                    {syncMutation.data.registered_count === 1 ? "" : "s"} from disk.
                  </p>
                )}
                {pipelinesQuery.isError && (
                  <p className="text-sm text-amber-300/90">
                    Could not load pipelines from the Lab API; showing the built-in registry. Restart{" "}
                    <code className="text-slate-200">./run-lab-api.sh</code> for live data.
                  </p>
                )}
                {library == null ? (
                  <p className="text-sm text-muted">Loading pipelines…</p>
                ) : pipelineGroups.length === 0 ? (
                  <p className="text-sm text-muted">
                    {groupFilter
                      ? "Nothing in this group is turned on."
                      : "Nothing is turned on. Pick a full pipeline in the library and choose Turn on."}
                  </p>
                ) : (
                  <div className="space-y-4">
                    {pipelineGroups.map((entry) => (
                      <Card key={entry.group.id} className="!p-4">
                        <h3 className="font-medium text-white">{entry.group.title}</h3>
                        <p className="mt-2 text-sm leading-relaxed text-muted">{entry.group.summary}</p>
                        <div className="mt-4 space-y-4">
                          {entry.pipelines.map((pipeline) => (
                            <PipelineBlock
                              key={pipeline.id}
                              pipeline={pipeline}
                              titleOverride={library.titles[pipeline.id]}
                              experiments={experimentsByPipeline.get(pipeline.id) ?? []}
                              running={directPipelineMutation.isPending && runningPipelineId === pipeline.id}
                              runError={
                                runningPipelineId === pipeline.id && directPipelineMutation.isError
                                  ? directPipelineMutation.error instanceof Error
                                    ? directPipelineMutation.error.message
                                    : "Pipeline failed to start."
                                  : null
                              }
                              runningExperimentId={runningExperimentId}
                              onRunPipeline={(body) => {
                                setRunningPipelineId(pipeline.id);
                                directPipelineMutation.mutate(body);
                              }}
                              onRunExperiment={(experimentId, body) => {
                                setRunningExperimentId(experimentId);
                                pipelineMutation.mutate({ experiment_id: experimentId, ...body });
                              }}
                            />
                          ))}
                        </div>
                      </Card>
                    ))}
                  </div>
                )}
              </div>
              {library && (
                <PipelineLibrary
                  pipelines={pipelines}
                  library={library}
                  savedCounts={savedCounts}
                  onChange={updateLibrary}
                />
              )}
            </section>
          )}

          {section === "compares" && (
            <section id="compares" className="space-y-3">
              {(comparesQuery.data ?? []).length === 0 && (
                <p className="text-sm text-muted">
                  No compare sessions yet. Start one from{" "}
                  <button
                    type="button"
                    className="text-accent hover:underline"
                    onClick={() => openSection("run")}
                  >
                    Run
                  </button>
                  .
                </p>
              )}
              {(comparesQuery.data ?? []).map((row) => (
                <CompareSessionCard key={row.id} session={row} />
              ))}
            </section>
          )}
        </div>

        <div className="lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)] lg:self-start lg:overflow-y-auto">
          <JobMonitor activeJobId={jobId} onSelectJob={setJobId} />
        </div>
      </div>
    </div>
  );
}
