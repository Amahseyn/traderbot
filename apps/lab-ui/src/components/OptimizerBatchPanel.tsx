"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { JobErrorAlert } from "@/components/JobErrorAlert";
import { OptimizerDatasetSection } from "@/components/OptimizerDatasetSection";
import { StrategyMultiSelect } from "@/components/StrategyMultiSelect";
import { Button } from "@/components/ui/Button";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import { ErrorState, TableSkeleton } from "@/components/ui/States";
import { api } from "@/lib/api";

export function OptimizerBatchPanel({ onJob }: { onJob: (jobId: string) => void }) {
  const queryClient = useQueryClient();
  const datasetsQuery = useQuery({ queryKey: ["datasets"], queryFn: () => api.datasets(400) });
  const strategiesQuery = useQuery({
    queryKey: ["catalog-strategies"],
    queryFn: () => api.catalogStrategies(true),
  });

  const datasets = datasetsQuery.data ?? [];
  const strategies = strategiesQuery.data ?? [];

  const [datasetIds, setDatasetIds] = useState<Set<string>>(new Set());
  const [enabledStrategyIds, setEnabledStrategyIds] = useState<Set<string>>(new Set());
  const [trials, setTrials] = useState("80");
  const [fullGrid, setFullGrid] = useState(true);
  const [feePct, setFeePct] = useState("0.045");
  const [cash, setCash] = useState("10000");
  const [selectionMode, setSelectionMode] = useState<"validation" | "in_sample">("validation");
  const [visualize, setVisualize] = useState(true);

  useEffect(() => {
    if (enabledStrategyIds.size === 0 && strategies.length > 0) {
      setEnabledStrategyIds(new Set(strategies.map((row) => row.id)));
    }
  }, [strategies, enabledStrategyIds.size]);

  const blockers = useMemo(() => {
    const items: string[] = [];
    if (datasetIds.size === 0) items.push("Select at least one catalog dataset.");
    if (enabledStrategyIds.size === 0) items.push("Select at least one strategy.");
    if (Number(trials) < 1) items.push("Optuna trials must be at least 1.");
    return items;
  }, [datasetIds.size, enabledStrategyIds.size, trials]);

  const batchMutation = useMutation({
    mutationFn: () =>
      api.postJob("custom-research", {
        dataset_ids: [...datasetIds],
        compare_strategies: true,
        compare_mode: "strategies",
        optimize_before_compare: true,
        optimize_method: "optuna",
        optimize_n_trials: Number(trials),
        full_grid: fullGrid,
        optimize_selection_mode: selectionMode,
        use_optimized_strategy_params: true,
        apply_sweep_winner: true,
        strategy_ids: [...enabledStrategyIds],
        visualize,
        cash: Number(cash),
        fee: Number(feePct) / 100,
        execution: "close",
      }),
    onSuccess: (data) => {
      onJob(data.id);
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["sweeps"] });
    },
  });

  return (
    <div className="space-y-4">
      {datasetsQuery.isError && (
        <ErrorState title="Could not load datasets" error={datasetsQuery.error} hintAuth={false} />
      )}
      {strategiesQuery.isError && (
        <ErrorState title="Could not load strategies" error={strategiesQuery.error} hintAuth={false} />
      )}
      {datasetsQuery.isLoading ? (
        <TableSkeleton rows={3} />
      ) : (
        <OptimizerDatasetSection
          datasets={datasets}
          mode="multi"
          multiSelectedIds={datasetIds}
          onMultiSelectedIdsChange={setDatasetIds}
        />
      )}
      <Field label="Strategies">
        {strategiesQuery.isLoading ? (
          <TableSkeleton rows={2} />
        ) : (
          <StrategyMultiSelect
            strategies={strategies}
            enabledIds={enabledStrategyIds}
            onToggle={(id) => {
              setEnabledStrategyIds((previous) => {
                const next = new Set(previous);
                if (next.has(id)) next.delete(id);
                else next.add(id);
                return next;
              });
            }}
            onAddIds={(ids) => {
              setEnabledStrategyIds((previous) => {
                const next = new Set(previous);
                for (const id of ids) next.add(id);
                return next;
              });
            }}
            onClear={() => setEnabledStrategyIds(new Set())}
          />
        )}
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Optuna trials per strategy × file">
          <TextInput type="number" min={1} value={trials} onChange={(event) => setTrials(event.target.value)} />
        </Field>
        <Field label="Starting cash">
          <TextInput type="number" min={1} value={cash} onChange={(event) => setCash(event.target.value)} />
        </Field>
        <Field label="Fee per side (%)">
          <TextInput type="number" min={0} step="any" value={feePct} onChange={(event) => setFeePct(event.target.value)} />
        </Field>
        <Field label="Selection mode">
          <SelectInput
            value={selectionMode}
            onChange={(event) => setSelectionMode(event.target.value as "validation" | "in_sample")}
          >
            <option value="validation">Validation (recommended)</option>
            <option value="in_sample">In-sample</option>
          </SelectInput>
        </Field>
      </div>
      <label className="flex items-center gap-2 text-sm text-muted">
        <input type="checkbox" checked={fullGrid} onChange={(event) => setFullGrid(event.target.checked)} />
        Expanded built-in Optuna ranges (full grid hints)
      </label>
      <label className="flex items-center gap-2 text-sm text-muted">
        <input type="checkbox" checked={visualize} onChange={(event) => setVisualize(event.target.checked)} />
        Save compare charts on Runs
      </label>
      {blockers.length > 0 && (
        <ul className="list-disc pl-5 text-xs text-amber-100/90">
          {blockers.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
      <JobErrorAlert error={batchMutation.error} />
      <Button
        type="button"
        disabled={batchMutation.isPending || blockers.length > 0}
        onClick={() => batchMutation.mutate()}
      >
        {batchMutation.isPending ? "Starting batch…" : "Run batch Optuna + compare"}
      </Button>
    </div>
  );
}
