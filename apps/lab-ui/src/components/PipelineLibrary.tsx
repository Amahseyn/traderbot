"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { TextInput } from "@/components/ui/Field";
import type { PipelineSpecRow } from "@/lib/api";
import type { PipelineLibraryState } from "@/lib/pipelineLibrary";
import { isFullPipeline, pipelineLabel } from "@/lib/pipelines";

function LibraryRow({
  pipeline,
  active,
  savedCount,
  customTitle,
  onToggle,
  onRename,
}: {
  pipeline: PipelineSpecRow;
  active: boolean;
  savedCount: number;
  customTitle?: string;
  onToggle: () => void;
  onRename: (title: string) => void;
}) {
  const label = pipelineLabel(pipeline);
  const title = customTitle?.trim() || label.title;
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title);
  const steps = pipeline.steps ?? [];

  function saveName() {
    onRename(draft.trim());
    setEditing(false);
  }

  return (
    <div className="rounded-lg border border-border bg-surface/40 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {editing ? (
            <div className="flex flex-wrap items-center gap-2">
              <TextInput
                value={draft}
                aria-label="Pipeline name"
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") saveName();
                  if (event.key === "Escape") setEditing(false);
                }}
              />
              <Button onClick={saveName}>Save</Button>
              <Button variant="ghost" onClick={() => setEditing(false)}>
                Cancel
              </Button>
            </div>
          ) : (
            <div className="font-medium text-white">{title}</div>
          )}
          <p className="mt-1 text-sm leading-relaxed text-muted">{label.detail}</p>
          <p className="mt-1 font-mono text-xs text-muted">{pipeline.id}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {!editing && (
            <Button
              variant="ghost"
              onClick={() => {
                setDraft(title);
                setEditing(true);
              }}
            >
              Rename
            </Button>
          )}
          <Button variant={active ? "secondary" : "primary"} onClick={onToggle}>
            {active ? "Turn off" : "Turn on"}
          </Button>
        </div>
      </div>
      {steps.length > 0 && (
        <ol className="mt-3 flex flex-wrap items-center gap-2">
          {steps.map((step, index) => (
            <li key={step.id} className="flex items-center gap-2">
              <span className="rounded-full border border-border bg-panel px-3 py-1 text-xs text-slate-100">
                <span className="mr-1 text-muted">{index + 1}</span>
                {step.title}
              </span>
              {index < steps.length - 1 && <span className="text-muted">→</span>}
            </li>
          ))}
        </ol>
      )}
      {savedCount > 0 && (
        <p className="mt-2 text-xs text-muted">
          {active
            ? `${savedCount === 1 ? "1 saved config" : `${savedCount} saved configs`} under the active card above.`
            : `${savedCount === 1 ? "1 saved config" : `${savedCount} saved configs`}. Turn this pipeline on to run them.`}
        </p>
      )}
    </div>
  );
}

export function PipelineLibrary({
  pipelines,
  library,
  savedCounts,
  onChange,
}: {
  pipelines: PipelineSpecRow[];
  library: PipelineLibraryState;
  savedCounts: Map<string, number>;
  onChange: (next: PipelineLibraryState) => void;
}) {
  const active = new Set(library.activeIds);
  const full = pipelines.filter(isFullPipeline);
  const steps = pipelines.filter((pipeline) => !isFullPipeline(pipeline));

  function toggle(pipelineId: string) {
    const activeIds = active.has(pipelineId)
      ? library.activeIds.filter((id) => id !== pipelineId)
      : [...library.activeIds, pipelineId];
    onChange({ ...library, activeIds });
  }

  function rename(pipelineId: string, title: string) {
    const pipeline = pipelines.find((row) => row.id === pipelineId);
    const titles = { ...library.titles };
    if (!pipeline || !title || title === pipelineLabel(pipeline).title) {
      delete titles[pipelineId];
    } else {
      titles[pipelineId] = title;
    }
    onChange({ ...library, titles });
  }

  function rows(list: PipelineSpecRow[]) {
    return list.map((pipeline) => (
      <LibraryRow
        key={pipeline.id}
        pipeline={pipeline}
        active={active.has(pipeline.id)}
        savedCount={savedCounts.get(pipeline.id) ?? 0}
        customTitle={library.titles[pipeline.id]}
        onToggle={() => toggle(pipeline.id)}
        onRename={(title) => rename(pipeline.id, title)}
      />
    ));
  }

  return (
    <section className="space-y-4">
      <div>
        <h2 className="section-title">Library</h2>
        <p className="mt-1 text-sm text-muted">
          Turn a pipeline on to put its run form in Active. Rename only changes the label on this browser.
        </p>
      </div>
      <div>
        <h3 className="text-sm font-medium text-white">Full pipelines ({full.length})</h3>
        <p className="mt-1 text-sm text-muted">
          End-to-end jobs: download then score, or a whole desk on one file.
        </p>
        <div className="mt-3 space-y-3">{rows(full)}</div>
      </div>
      <details className="rounded-lg border border-border bg-panel/40 p-4">
        <summary className="cursor-pointer text-sm font-medium text-white">
          Single steps ({steps.length})
        </summary>
        <p className="mt-2 text-sm text-muted">
          One stage only. Turn one on if you want it in Active next to the full pipelines.
        </p>
        <div className="mt-3 space-y-3">{rows(steps)}</div>
      </details>
    </section>
  );
}
