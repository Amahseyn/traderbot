"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { JobErrorAlert } from "@/components/JobErrorAlert";
import { OptimizerDatasetSection } from "@/components/OptimizerDatasetSection";
import { Button } from "@/components/ui/Button";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import { api, type StrategyParamField } from "@/lib/api";
import {
  loadOptimizerSweepDraft,
  saveOptimizerSweepDraft,
  type OptimizerSweepDraft,
} from "@/lib/optimizerDraft";
import { parseSweepValues, prettyParamLabel } from "@/lib/sweepFormUtils";
import { ErrorState, TableSkeleton } from "@/components/ui/States";

function SweepBaseParamsFields({
  fields,
  values,
  onChange,
}: {
  fields: StrategyParamField[];
  values: Record<string, unknown>;
  onChange: (name: string, value: unknown) => void;
}) {
  if (fields.length === 0) {
    return <p className="text-sm text-muted">No tunable parameters for this strategy.</p>;
  }
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {fields.map((field) => {
        const value = values[field.name];
        const label = prettyParamLabel(field.name);
        if (field.kind === "bool") {
          return (
            <label key={field.name} className="flex items-center gap-2 text-sm text-slate-200">
              <input
                type="checkbox"
                checked={value === true}
                onChange={(event) => onChange(field.name, event.target.checked)}
              />
              {label}
            </label>
          );
        }
        if (field.kind === "string") {
          return (
            <Field key={field.name} label={label}>
              <TextInput
                value={value == null ? "" : String(value)}
                onChange={(event) => onChange(field.name, event.target.value)}
              />
            </Field>
          );
        }
        return (
          <Field key={field.name} label={label}>
            <TextInput
              type="number"
              step={field.kind === "int" ? 1 : "any"}
              value={value == null || value === "" ? "" : String(value)}
              onChange={(event) =>
                onChange(field.name, event.target.value === "" ? null : Number(event.target.value))
              }
            />
          </Field>
        );
      })}
    </div>
  );
}

function EmptyDatasets({ failed = false }: { failed?: boolean }) {
  return (
    <div className="rounded-lg border border-dashed border-border bg-panel/30 px-4 py-6 text-center text-sm text-muted">
      <p>No datasets in the catalog yet.</p>
      <p className="mt-2">
        {failed ? "Fix the API error above, or " : ""}
        <Link href="/data" className="text-accent hover:underline">export OHLC on Data</Link>
        {" "}before running an optimizer job.
      </p>
    </div>
  );
}

export type StrategySweepSelection = {
  datasetId: string;
  strategyId: string;
  symbol: string | null;
  resolution: string | null;
};

type StrategySweepFormProps = {
  onJob: (jobId: string) => void;
  onSelectionChange?: (selection: StrategySweepSelection) => void;
  persistDraft?: boolean;
  submitLabel?: string;
};

export function StrategySweepForm({
  onJob,
  onSelectionChange,
  persistDraft = true,
  submitLabel = "Start optimizer",
}: StrategySweepFormProps) {
  const [sweepDatasetId, setSweepDatasetId] = useState("");
  const [sweepStrategyId, setSweepStrategyId] = useState("");
  const [sweepParamA, setSweepParamA] = useState("fast");
  const [sweepValuesA, setSweepValuesA] = useState("5, 10, 20");
  const [sweepUseSecondParam, setSweepUseSecondParam] = useState(true);
  const [sweepParamB, setSweepParamB] = useState("slow");
  const [sweepValuesB, setSweepValuesB] = useState("20, 50");
  const [sweepCash, setSweepCash] = useState("10000");
  const [sweepFee, setSweepFee] = useState("0.045");
  const [sweepSelectionMode, setSweepSelectionMode] = useState<"validation" | "in_sample">("validation");
  const [sweepHoldout, setSweepHoldout] = useState("");
  const [sweepMinTrades, setSweepMinTrades] = useState("0");
  const [sweepMaxCombos, setSweepMaxCombos] = useState("64");
  const [sweepFullGrid, setSweepFullGrid] = useState(true);
  const [sweepOptimizeMethod, setSweepOptimizeMethod] = useState<"grid" | "optuna">("optuna");
  const [sweepOptunaTrials, setSweepOptunaTrials] = useState("80");
  const [sweepBase, setSweepBase] = useState<Record<string, unknown>>({});
  const [sweepBaseFor, setSweepBaseFor] = useState("");
  const [showSweepBase, setShowSweepBase] = useState(false);
  const [sweepGridAppliedFor, setSweepGridAppliedFor] = useState("");
  const [formReady, setFormReady] = useState(false);
  const [draftRestored, setDraftRestored] = useState(false);

  useEffect(() => {
    if (!persistDraft) {
      setFormReady(true);
      return;
    }
    const draft = loadOptimizerSweepDraft();
    if (draft) {
      setSweepDatasetId(draft.sweepDatasetId);
      setSweepStrategyId(draft.sweepStrategyId);
      setSweepParamA(draft.sweepParamA);
      setSweepValuesA(draft.sweepValuesA);
      setSweepUseSecondParam(draft.sweepUseSecondParam);
      setSweepParamB(draft.sweepParamB);
      setSweepValuesB(draft.sweepValuesB);
      setSweepCash(draft.sweepCash);
      setSweepFee(draft.sweepFee);
      setSweepSelectionMode(draft.sweepSelectionMode);
      setSweepHoldout(draft.sweepHoldout);
      setSweepMinTrades(draft.sweepMinTrades);
      setSweepMaxCombos(draft.sweepMaxCombos);
      setSweepFullGrid(draft.sweepFullGrid);
      setSweepOptimizeMethod(draft.sweepOptimizeMethod);
      setSweepOptunaTrials(draft.sweepOptunaTrials);
      setDraftRestored(true);
    }
    setFormReady(true);
  }, [persistDraft]);

  const datasetsQuery = useQuery({ queryKey: ["datasets"], queryFn: () => api.datasets(300) });
  const strategiesQuery = useQuery({
    queryKey: ["catalog-strategies"],
    queryFn: () => api.catalogStrategies(true),
  });

  const datasetOptions = datasetsQuery.data ?? [];
  const catalogStrategies = strategiesQuery.data ?? [];

  useEffect(() => {
    if (!sweepDatasetId && datasetOptions[0]) {
      setSweepDatasetId(datasetOptions[0].id);
    }
  }, [datasetOptions, sweepDatasetId]);

  useEffect(() => {
    if (!catalogStrategies.some((strategy) => strategy.id === sweepStrategyId) && catalogStrategies[0]) {
      setSweepStrategyId(catalogStrategies[0].id);
    }
  }, [catalogStrategies, sweepStrategyId]);

  const sweepDataset = datasetOptions.find((dataset) => dataset.id === sweepDatasetId);

  useEffect(() => {
    onSelectionChange?.({
      datasetId: sweepDatasetId,
      strategyId: sweepStrategyId,
      symbol: sweepDataset?.symbol ?? null,
      resolution: sweepDataset?.resolution ?? null,
    });
  }, [sweepDatasetId, sweepStrategyId, sweepDataset?.symbol, sweepDataset?.resolution, onSelectionChange]);

  useEffect(() => {
    if (!persistDraft || !formReady) return;
    const payload: OptimizerSweepDraft = {
      version: 1,
      sweepDatasetId,
      sweepStrategyId,
      sweepParamA,
      sweepValuesA,
      sweepUseSecondParam,
      sweepParamB,
      sweepValuesB,
      sweepCash,
      sweepFee,
      sweepSelectionMode,
      sweepHoldout,
      sweepMinTrades,
      sweepMaxCombos,
      sweepFullGrid,
      sweepOptimizeMethod,
      sweepOptunaTrials,
    };
    saveOptimizerSweepDraft(payload);
  }, [
    formReady,
    persistDraft,
    sweepDatasetId,
    sweepStrategyId,
    sweepParamA,
    sweepValuesA,
    sweepUseSecondParam,
    sweepParamB,
    sweepValuesB,
    sweepCash,
    sweepFee,
    sweepSelectionMode,
    sweepHoldout,
    sweepMinTrades,
    sweepMaxCombos,
    sweepFullGrid,
    sweepOptimizeMethod,
    sweepOptunaTrials,
  ]);

  const bestSweepQuery = useQuery({
    queryKey: ["best-sweep", sweepStrategyId, sweepDataset?.symbol, sweepDataset?.resolution],
    queryFn: () =>
      api.bestSweep(
        sweepStrategyId,
        sweepDataset?.symbol ?? undefined,
        sweepDataset?.resolution ?? undefined,
      ),
    enabled: Boolean(sweepStrategyId),
    retry: false,
    staleTime: 30_000,
  });
  const sweepBestParams: Record<string, unknown> = bestSweepQuery.data?.best_params ?? {};

  const strategyParamsQuery = useQuery({
    queryKey: ["strategy-params", sweepStrategyId],
    queryFn: () => api.strategyParams(sweepStrategyId),
    enabled: Boolean(sweepStrategyId),
    staleTime: 60_000,
  });
  const tuneGridQuery = useQuery({
    queryKey: ["strategy-tune-grid", sweepStrategyId, sweepFullGrid],
    queryFn: () => api.strategyTuneGrid(sweepStrategyId, sweepFullGrid),
    enabled: Boolean(sweepStrategyId),
    staleTime: 60_000,
  });
  const sweepParamFields = strategyParamsQuery.data?.params ?? [];
  const sweepParamNames = sweepParamFields.map((field) => field.name);

  useEffect(() => {
    setSweepGridAppliedFor("");
  }, [sweepStrategyId, sweepFullGrid]);

  useEffect(() => {
    const grid = tuneGridQuery.data?.param_grid;
    if (!grid || !sweepStrategyId) return;
    const signature = `${sweepStrategyId}:${sweepFullGrid}:${JSON.stringify(grid)}`;
    if (sweepGridAppliedFor === signature) return;
    const keys = Object.keys(grid);
    if (keys.length === 0) return;
    setSweepParamA(keys[0]);
    setSweepValuesA((grid[keys[0]] ?? []).map(String).join(", "));
    if (keys.length > 1) {
      setSweepUseSecondParam(true);
      setSweepParamB(keys[1]);
      setSweepValuesB((grid[keys[1]] ?? []).map(String).join(", "));
    } else {
      setSweepUseSecondParam(false);
      setSweepParamB("");
      setSweepValuesB("");
    }
    setSweepGridAppliedFor(signature);
  }, [tuneGridQuery.data, sweepStrategyId, sweepFullGrid, sweepGridAppliedFor]);

  function sweepValuesForParam(name: string, currentText: string): string {
    const field = sweepParamFields.find((entry) => entry.name === name);
    const parsed = parseSweepValues(currentText);
    if (field?.kind === "bool") {
      if (parsed.length > 0 && parsed.every((value) => typeof value === "boolean")) return currentText;
      return "true, false";
    }
    if (parsed.length > 0 && parsed.every((value) => typeof value === "number")) return currentText;
    const fallback = field?.default;
    return fallback == null ? "" : String(fallback);
  }

  useEffect(() => {
    const names = (strategyParamsQuery.data?.params ?? []).map((field) => field.name);
    if (names.length === 0) return;
    const nextA = names.includes(sweepParamA) ? sweepParamA : names[0];
    if (nextA !== sweepParamA) {
      setSweepParamA(nextA);
      setSweepValuesA((current) => sweepValuesForParam(nextA, current));
      return;
    }
    const secondChoices = names.filter((name) => name !== nextA);
    if (!sweepParamB || !secondChoices.includes(sweepParamB)) {
      const fallback = secondChoices[0] ?? "";
      setSweepParamB(fallback);
      if (fallback) setSweepValuesB((current) => sweepValuesForParam(fallback, current));
    }
  }, [strategyParamsQuery.data, sweepParamA, sweepParamB, sweepParamFields]);

  useEffect(() => {
    const fields = strategyParamsQuery.data?.params;
    if (!sweepStrategyId || !fields || sweepBaseFor === sweepStrategyId) return;
    const initial: Record<string, unknown> = {};
    for (const field of fields) initial[field.name] = field.default ?? null;
    setSweepBase(initial);
    setSweepBaseFor(sweepStrategyId);
  }, [strategyParamsQuery.data, sweepStrategyId, sweepBaseFor]);

  function sweepOptimumText(paramName: string): string | null {
    const value = sweepBestParams[paramName];
    if (value == null) return null;
    return `Optimum from last sweep: ${paramName} = ${String(value)}`;
  }

  function sweepValuesHint(valuesText: string, paramName: string, placeholder: string): string {
    const parts: string[] = [];
    const count = parseSweepValues(valuesText).length;
    parts.push(count > 0 ? `${count} values` : placeholder);
    const optimum = sweepOptimumText(paramName);
    if (optimum) parts.push(optimum);
    return parts.join(" · ");
  }

  const sweepValuesPreviewA = parseSweepValues(sweepValuesA);
  const sweepValuesPreviewB = parseSweepValues(sweepValuesB);

  const sweepMutation = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        dataset_id: sweepDatasetId,
        mode: "strategies",
        strategy_id: sweepStrategyId,
        full_grid: sweepFullGrid,
        optimize_method: sweepOptimizeMethod,
        optimize_selection_mode: sweepSelectionMode,
        ...sweepBase,
        cash: Number(sweepCash),
        fee: Number(sweepFee) / 100,
        holdout_tail_bars: sweepHoldout === "" ? null : Number(sweepHoldout),
        min_trades: Number(sweepMinTrades),
        max_combos: Number(sweepMaxCombos),
      };
      if (sweepOptimizeMethod === "optuna") {
        body.optimize_n_trials = Number(sweepOptunaTrials);
      } else {
        const params: Record<string, unknown[]> = { [sweepParamA]: parseSweepValues(sweepValuesA) };
        if (sweepUseSecondParam && sweepParamB && sweepParamB !== sweepParamA) {
          const second = parseSweepValues(sweepValuesB);
          if (second.length > 0) params[sweepParamB] = second;
        }
        body.params = params;
      }
      return api.postJob("strategy-sweep", body);
    },
    onSuccess: (data) => onJob(data.id),
  });

  const sweepReady =
    Boolean(sweepDatasetId) &&
    Boolean(sweepStrategyId) &&
    (sweepOptimizeMethod === "optuna"
      ? Number(sweepOptunaTrials) >= 1
      : sweepValuesPreviewA.length > 0 &&
        (!sweepUseSecondParam || sweepValuesPreviewB.length > 0));

  const storedSweepSummary = useMemo(() => {
    if (!bestSweepQuery.data) return null;
    const metrics = bestSweepQuery.data.best_metrics ?? {};
    const ret = metrics.return_pct;
    const hold = metrics.holdout_return_pct;
    const parts: string[] = [];
    if (ret != null) parts.push(`validation ${Number(ret).toFixed(2)}%`);
    if (hold != null) parts.push(`holdout ${Number(hold).toFixed(2)}%`);
    return parts.length ? parts.join(" · ") : null;
  }, [bestSweepQuery.data]);

  return (
    <div className="space-y-4">
      {datasetsQuery.isError && (
        <ErrorState title="Could not load datasets" error={datasetsQuery.error} hintAuth={false} />
      )}
      {strategiesQuery.isError && (
        <ErrorState title="Could not load strategies" error={strategiesQuery.error} hintAuth={false} />
      )}
      {draftRestored && (
        <p className="text-xs text-muted">Restored your last optimizer settings from this browser.</p>
      )}
      {datasetsQuery.isLoading ? (
        <TableSkeleton rows={3} />
      ) : datasetOptions.length === 0 ? (
        <EmptyDatasets failed={datasetsQuery.isError} />
      ) : (
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            setDraftRestored(false);
            sweepMutation.mutate();
          }}
        >
          <OptimizerDatasetSection
            datasets={datasetOptions}
            mode="single"
            singleDatasetId={sweepDatasetId}
            onSingleDatasetIdChange={setSweepDatasetId}
          />
          <Field label="Strategy">
            <SelectInput value={sweepStrategyId} onChange={(event) => setSweepStrategyId(event.target.value)}>
              {catalogStrategies.map((strategy) => (
                <option key={strategy.id} value={strategy.id}>
                  {strategy.name || strategy.id}
                </option>
              ))}
            </SelectInput>
          </Field>
          {storedSweepSummary && (
            <p className="text-xs text-muted">
              Stored best for this market: {storedSweepSummary}
            </p>
          )}
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Optimizer">
              <SelectInput
                value={sweepOptimizeMethod}
                onChange={(event) => setSweepOptimizeMethod(event.target.value as "grid" | "optuna")}
              >
                <option value="optuna">Optuna (all strategy params)</option>
                <option value="grid">Grid (1–2 params)</option>
              </SelectInput>
            </Field>
            {sweepOptimizeMethod === "optuna" ? (
              <Field label="Optuna trials" hint="More trials = slower, often better fit.">
                <TextInput
                  type="number"
                  min={1}
                  value={sweepOptunaTrials}
                  onChange={(event) => setSweepOptunaTrials(event.target.value)}
                />
              </Field>
            ) : null}
          </div>
          <label className="flex items-center gap-2 text-sm text-muted">
            <input
              type="checkbox"
              checked={sweepFullGrid}
              onChange={(event) => setSweepFullGrid(event.target.checked)}
            />
            Expanded built-in ranges (wider Optuna hints / grid lists)
          </label>
          {tuneGridQuery.isFetching && (
            <p className="text-sm text-muted">Loading default grid for this strategy…</p>
          )}
          {sweepOptimizeMethod === "grid" && (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Parameter 1">
                  <SelectInput
                    value={sweepParamA}
                    onChange={(event) => {
                      const next = event.target.value;
                      setSweepParamA(next);
                      setSweepValuesA((current) => sweepValuesForParam(next, current));
                    }}
                  >
                    {sweepParamNames.map((name) => (
                      <option key={name} value={name}>
                        {name}
                      </option>
                    ))}
                  </SelectInput>
                </Field>
                <Field
                  label="Values 1"
                  hint={sweepValuesHint(sweepValuesA, sweepParamA, "Comma-separated, e.g. 5, 10, 20")}
                >
                  <TextInput
                    value={sweepValuesA}
                    onChange={(event) => setSweepValuesA(event.target.value)}
                    placeholder="5, 10, 20"
                  />
                </Field>
              </div>
              <label className="flex items-center gap-2 text-sm text-muted">
                <input
                  type="checkbox"
                  checked={sweepUseSecondParam}
                  onChange={(event) => setSweepUseSecondParam(event.target.checked)}
                />
                Sweep a second parameter (max 2)
              </label>
              {sweepUseSecondParam && (
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Parameter 2">
                    <SelectInput
                      value={sweepParamB}
                      onChange={(event) => {
                        const next = event.target.value;
                        setSweepParamB(next);
                        setSweepValuesB((current) => sweepValuesForParam(next, current));
                      }}
                    >
                      {sweepParamNames
                        .filter((name) => name !== sweepParamA)
                        .map((name) => (
                          <option key={name} value={name}>
                            {name}
                          </option>
                        ))}
                    </SelectInput>
                  </Field>
                  <Field
                    label="Values 2"
                    hint={sweepValuesHint(sweepValuesB, sweepParamB, "Comma-separated")}
                  >
                    <TextInput
                      value={sweepValuesB}
                      onChange={(event) => setSweepValuesB(event.target.value)}
                      placeholder="20, 50"
                    />
                  </Field>
                </div>
              )}
            </>
          )}
          <button
            type="button"
            className="text-sm text-accent hover:underline"
            onClick={() => setShowSweepBase((open) => !open)}
          >
            {showSweepBase
              ? "Hide base strategy parameters"
              : sweepOptimizeMethod === "optuna"
                ? "Fixed strategy parameters (not tuned by Optuna)"
                : "Base strategy parameters (used for every knob outside the grid)"}
          </button>
          {showSweepBase &&
            (strategyParamsQuery.isLoading ? (
              <TableSkeleton rows={2} />
            ) : (
              <SweepBaseParamsFields
                fields={sweepParamFields}
                values={sweepBase}
                onChange={(name, value) => setSweepBase((current) => ({ ...current, [name]: value }))}
              />
            ))}
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Starting cash">
              <TextInput
                type="number"
                min={1}
                value={sweepCash}
                onChange={(event) => setSweepCash(event.target.value)}
              />
            </Field>
            <Field label="Fee per side (%)" hint="Hyperliquid perp taker default: 0.045%.">
              <TextInput
                type="number"
                min={0}
                step="any"
                value={sweepFee}
                onChange={(event) => setSweepFee(event.target.value)}
              />
            </Field>
            <Field
              label="Selection mode"
              hint="Validation splits the dataset chronologically; in-sample ranks on the training window only."
            >
              <SelectInput
                value={sweepSelectionMode}
                onChange={(event) => setSweepSelectionMode(event.target.value as "validation" | "in_sample")}
              >
                <option value="validation">Validation (recommended)</option>
                <option value="in_sample">In-sample (legacy)</option>
              </SelectInput>
            </Field>
            <Field
              label="Holdout bars"
              hint="In-sample / fallback only: trailing bars for holdout report."
            >
              <TextInput
                type="number"
                min={1}
                value={sweepHoldout}
                onChange={(event) => setSweepHoldout(event.target.value)}
                placeholder="e.g. 50"
                disabled={sweepSelectionMode === "validation"}
              />
            </Field>
            <Field label="Min trades" hint="Combos with fewer trades rank lower.">
              <TextInput
                type="number"
                min={0}
                value={sweepMinTrades}
                onChange={(event) => setSweepMinTrades(event.target.value)}
              />
            </Field>
            <Field label="Max combos" hint="Guard against huge grids.">
              <TextInput
                type="number"
                min={1}
                value={sweepMaxCombos}
                onChange={(event) => setSweepMaxCombos(event.target.value)}
              />
            </Field>
          </div>
          <JobErrorAlert error={sweepMutation.error} />
          <Button type="submit" disabled={sweepMutation.isPending || !sweepReady}>
            {sweepMutation.isPending ? "Starting…" : submitLabel}
          </Button>
        </form>
      )}
    </div>
  );
}
