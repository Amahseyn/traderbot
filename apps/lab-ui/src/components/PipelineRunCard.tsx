"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import { api, type PipelineInputView, type PipelineSpecRow } from "@/lib/api";
import { pipelineLabel } from "@/lib/pipelines";

function inputDefault(field: PipelineInputView): string {
  return field.default ?? "";
}

export function PipelineRunCard({
  pipeline,
  running,
  error,
  titleOverride,
  onRun,
}: {
  pipeline: PipelineSpecRow;
  running: boolean;
  error?: string | null;
  titleOverride?: string;
  onRun: (body: Record<string, unknown>) => void;
}) {
  const label = pipelineLabel(pipeline);
  const title = titleOverride?.trim() || label.title;
  const steps = pipeline.steps ?? [];
  const inputs = pipeline.inputs ?? [];
  const datasetsQuery = useQuery({
    queryKey: ["datasets"],
    queryFn: () => api.datasets(),
    enabled: inputs.some((field) => field.kind === "dataset"),
  });
  const datasets = datasetsQuery.data ?? [];

  const [values, setValues] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    for (const field of inputs) {
      initial[field.key] = inputDefault(field);
    }
    return initial;
  });

  const allAssets = values.all_assets !== "false";
  const hasAllAssets = inputs.some((field) => field.key === "all_assets");
  const datasetField = inputs.find((field) => field.kind === "dataset");
  const showDataset = Boolean(datasetField) && (!hasAllAssets || !allAssets);

  const datasetId = values.dataset || datasets[0]?.id || "";
  const missingDataset = showDataset && datasets.length === 0;

  const body = useMemo(() => {
    const payload: Record<string, unknown> = { pipeline_id: pipeline.id };
    for (const field of inputs) {
      if (field.kind === "number") {
        payload[field.key] = Number(values[field.key] || field.default || "0");
      }
      if (field.kind === "boolean") {
        payload[field.key] = (values[field.key] ?? field.default) !== "false";
      }
      if (field.kind === "select") {
        payload[field.key] = values[field.key] || field.default || "";
      }
    }
    if (showDataset && datasetId) {
      payload.dataset_id = datasetId;
    }
    return payload;
  }, [datasetId, inputs, pipeline.id, showDataset, values]);

  return (
    <div className="rounded-lg border border-border bg-surface/40 p-4">
      <div className="font-medium text-white">{title}</div>
      <p className="mt-1 text-sm leading-relaxed text-muted">{label.detail}</p>
      <p className="mt-1 font-mono text-xs text-muted">{pipeline.id}</p>
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
      <div className="mt-4 flex flex-wrap items-end gap-3">
        {inputs.map((field) => {
          if (field.kind === "number") {
            return (
              <Field key={field.key} label={field.label} hint={field.hint}>
                <TextInput
                  type="number"
                  min={1}
                  value={values[field.key] ?? ""}
                  onChange={(event) =>
                    setValues((current) => ({ ...current, [field.key]: event.target.value }))
                  }
                />
              </Field>
            );
          }
          if (field.kind === "select") {
            return (
              <Field key={field.key} label={field.label} hint={field.hint}>
                <SelectInput
                  value={values[field.key] ?? field.default ?? ""}
                  onChange={(event) =>
                    setValues((current) => ({ ...current, [field.key]: event.target.value }))
                  }
                >
                  {(field.options ?? []).map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </SelectInput>
              </Field>
            );
          }
          if (field.kind === "boolean") {
            return (
              <label key={field.key} className="flex items-center gap-2 pb-2 text-sm text-slate-200">
                <input
                  type="checkbox"
                  checked={(values[field.key] ?? field.default) !== "false"}
                  onChange={(event) =>
                    setValues((current) => ({
                      ...current,
                      [field.key]: event.target.checked ? "true" : "false",
                    }))
                  }
                />
                {field.label}
              </label>
            );
          }
          return null;
        })}
        {showDataset && datasets.length > 0 && (
          <Field label={datasetField?.label ?? "Price file"} hint={datasetField?.hint}>
            <SelectInput
              value={datasetId}
              onChange={(event) => setValues((current) => ({ ...current, dataset: event.target.value }))}
            >
              {datasets.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.label}
                </option>
              ))}
            </SelectInput>
          </Field>
        )}
        {steps.length > 0 && (
          <Button disabled={running || missingDataset} onClick={() => onRun(body)}>
            {running ? "Starting…" : "Run pipeline"}
          </Button>
        )}
      </div>
      {error && <p className="mt-2 text-sm text-red-400">{error}</p>}
      {inputs.some((field) => field.kind === "boolean" && field.hint) && (
        <p className="mt-2 text-xs text-muted">
          {inputs.find((field) => field.kind === "boolean")?.hint}
        </p>
      )}
      {missingDataset && (
        <p className="mt-3 text-sm text-muted">
          No price files in the catalog yet.{" "}
          <Link href="/data" className="text-accent hover:underline">
            Export one on Data
          </Link>
          .
        </p>
      )}
    </div>
  );
}
