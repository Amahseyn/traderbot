"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { JobErrorAlert } from "@/components/JobErrorAlert";
import { JobMonitor } from "@/components/JobMonitor";
import {
  PipelineDataSection,
  pipelineDataSourceReady,
  type PipelineDataSectionState,
} from "@/components/PipelineDataSection";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { api } from "@/lib/api";
import {
  datetimeLocalToUtcIso,
  formatBarIntervalHint,
  minutesFromResolution,
  utcDateToDatetimeLocal,
} from "@/lib/format";

const INITIAL_DATA_STATE: PipelineDataSectionState = {
  dataSourceMode: "existing",
  exportDays: "30",
  exportMarketSymbol: "",
  exportInterval: "60",
  useAllHourly: false,
  datasetIds: [],
  catalogSearch: "",
  catalogSymbol: "",
  catalogResolution: "",
  marketScope: "nobitex_all",
  marketSearch: "",
};

function StrategyMultiSelect({
  strategies,
  enabledIds,
  onToggle,
}: {
  strategies: Array<{ id: string; name: string }>;
  enabledIds: Set<string>;
  onToggle: (id: string) => void;
}) {
  return (
    <div className="max-h-40 space-y-1 overflow-y-auto rounded-lg border border-border bg-surface p-2">
      {strategies.map((strategy) => (
        <label key={strategy.id} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm hover:bg-panel">
          <input
            type="checkbox"
            checked={enabledIds.has(strategy.id)}
            onChange={() => onToggle(strategy.id)}
          />
          <span className="text-slate-200">{strategy.name || strategy.id}</span>
        </label>
      ))}
      <p className="px-2 pt-1 text-xs text-muted">
        Uncheck strategies to skip them. Use “Max strategies” to cap how many run (catalog order).
      </p>
    </div>
  );
}

export default function CustomPipelinePage() {
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const [dataState, setDataState] = useState<PipelineDataSectionState>(INITIAL_DATA_STATE);

  const [compareStrategies, setCompareStrategies] = useState(true);
  const [maxStrategies, setMaxStrategies] = useState("");
  const [enabledStrategyIds, setEnabledStrategyIds] = useState<Set<string>>(new Set());

  const [cash, setCash] = useState("10000");
  const [visualize, setVisualize] = useState(true);
  const [limitRunWindow, setLimitRunWindow] = useState(false);
  const [runStartLocal, setRunStartLocal] = useState("");
  const [runEndLocal, setRunEndLocal] = useState("");

  const datasetsQuery = useQuery({ queryKey: ["datasets"], queryFn: () => api.datasets(300) });
  const strategiesQuery = useQuery({
    queryKey: ["catalog-strategies"],
    queryFn: () => api.catalogStrategies(true),
  });
  const ruleStrategies = useMemo(
    () => (strategiesQuery.data ?? []).filter((row) => row.style !== "ml"),
    [strategiesQuery.data],
  );

  useEffect(() => {
    if (ruleStrategies.length === 0) return;
    setEnabledStrategyIds(new Set(ruleStrategies.map((row) => row.id)));
  }, [ruleStrategies]);

  function patchDataState(patch: Partial<PipelineDataSectionState>) {
    setDataState((previous) => ({ ...previous, ...patch }));
  }

  function toggleStrategy(id: string) {
    setEnabledStrategyIds((previous) => {
      const next = new Set(previous);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  const firstDataset = datasetsQuery.data?.find((row) => dataState.datasetIds.includes(row.id));
  const selectedDatasets = useMemo(
    () => (datasetsQuery.data ?? []).filter((row) => dataState.datasetIds.includes(row.id)),
    [datasetsQuery.data, dataState.datasetIds],
  );
  const candleMinutes = minutesFromResolution(firstDataset?.resolution) ?? 60;
  const runWindowCatalogHint = useMemo(() => {
    if (selectedDatasets.length === 0) {
      return "Pick datasets in step 1 to see catalog date bounds, or enter times manually.";
    }
    const starts = selectedDatasets.map((row) => row.range_start_utc).filter(Boolean) as string[];
    const ends = selectedDatasets.map((row) => row.range_end_utc).filter(Boolean) as string[];
    if (starts.length === 0 && ends.length === 0) {
      return `Bounds use ${formatBarIntervalHint(candleMinutes)}; leave empty to use the full file.`;
    }
    const startLabel = starts.length ? starts.map((value) => value.slice(0, 10)).join(", ") : "—";
    const endLabel = ends.length ? ends.map((value) => value.slice(0, 10)).join(", ") : "—";
    return `Catalog coverage (dates): ${startLabel} → ${endLabel}. Times snap to closed ${formatBarIntervalHint(candleMinutes)}.`;
  }, [selectedDatasets, candleMinutes]);

  useEffect(() => {
    if (!limitRunWindow || selectedDatasets.length !== 1) return;
    const only = selectedDatasets[0];
    if (!runStartLocal && only.range_start_utc) {
      setRunStartLocal(utcDateToDatetimeLocal(only.range_start_utc));
    }
    if (!runEndLocal && only.range_end_utc) {
      setRunEndLocal(utcDateToDatetimeLocal(only.range_end_utc));
    }
  }, [limitRunWindow, selectedDatasets, runStartLocal, runEndLocal]);

  const runMutation = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        export_days: Number(dataState.exportDays),
        use_all_hourly_files: dataState.useAllHourly,
        dataset_ids: dataState.datasetIds,
        compare_strategies: compareStrategies,
        run_forecasts: false,
        visualize,
        cash: Number(cash),
      };
      if (dataState.dataSourceMode === "download" && dataState.exportMarketSymbol.trim()) {
        body.export_market_symbol = dataState.exportMarketSymbol.trim();
        body.interval = dataState.exportInterval;
      }
      if (maxStrategies.trim()) {
        body.max_strategies = Number(maxStrategies);
      }
      if (enabledStrategyIds.size > 0 && enabledStrategyIds.size < ruleStrategies.length) {
        body.strategy_ids = [...enabledStrategyIds];
      }
      if (enabledStrategyIds.size === 0) {
        throw new Error("Select at least one strategy");
      }
      if (limitRunWindow) {
        const runStartUtc = datetimeLocalToUtcIso(runStartLocal);
        const runEndUtc = datetimeLocalToUtcIso(runEndLocal);
        if (!runStartUtc && !runEndUtc) {
          throw new Error("Set a start time, end time, or both for the run window");
        }
        if (runStartUtc) body.run_start_utc = runStartUtc;
        if (runEndUtc) body.run_end_utc = runEndUtc;
      }
      return api.postJob("custom-research", body);
    },
    onSuccess: (data) => {
      setJobId(data.id);
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  const canRun =
    compareStrategies &&
    pipelineDataSourceReady(dataState) &&
    enabledStrategyIds.size > 0 &&
    (!limitRunWindow ||
      Boolean(datetimeLocalToUtcIso(runStartLocal) || datetimeLocalToUtcIso(runEndLocal)));

  return (
    <div className="space-y-8 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(18rem,22rem)] lg:items-start lg:gap-8">
      <div className="space-y-8 min-w-0">
      <PageHeader
        eyebrow="Research loop"
        title="Custom pipeline"
        description="Configure an end-to-end run: download or pick OHLC files, then compare rule-based strategies (with a cap or subset)."
      />

      <form
        className="space-y-6"
        onSubmit={(event) => {
          event.preventDefault();
          runMutation.mutate();
        }}
      >
        <Card
          title="1 · Data"
          description="Filter the catalog or download from Nobitex as part of this pipeline."
        >
          <PipelineDataSection
            state={dataState}
            onChange={patchDataState}
            onExportJobStarted={setJobId}
          />
        </Card>

        <Card title="2 · Strategies" description="Compare rule-based strategies on each selected file.">
          <div className="space-y-4">
            <label className="flex items-center gap-2 text-sm text-slate-200">
              <input
                type="checkbox"
                checked={compareStrategies}
                onChange={(event) => setCompareStrategies(event.target.checked)}
              />
              Run strategy compare
            </label>
            {compareStrategies && (
              <>
                <div className="max-w-xs">
                  <Field
                    label="Max strategies"
                    hint="Optional. Runs only the first N strategies in catalog order when set."
                  >
                    <TextInput
                      type="number"
                      min={1}
                      placeholder="All"
                      value={maxStrategies}
                      onChange={(event) => setMaxStrategies(event.target.value)}
                    />
                  </Field>
                </div>
                <Field label="Strategies">
                  {strategiesQuery.isLoading ? (
                    <p className="text-sm text-muted">Loading strategies…</p>
                  ) : (
                    <StrategyMultiSelect
                      strategies={ruleStrategies}
                      enabledIds={enabledStrategyIds}
                      onToggle={toggleStrategy}
                    />
                  )}
                </Field>
              </>
            )}
          </div>
        </Card>

        <Card
          title="3 · Simulation"
          description="Backtest settings and optional time window for compare on each file."
        >
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Starting cash (compare)">
                <TextInput type="number" min={1} value={cash} onChange={(event) => setCash(event.target.value)} />
              </Field>
              <label className="flex items-center gap-2 self-end text-sm text-muted pb-2">
                <input
                  type="checkbox"
                  checked={visualize}
                  onChange={(event) => setVisualize(event.target.checked)}
                />
                Save compare charts
              </label>
            </div>

            <div className="panel-inset space-y-3">
              <label className="flex items-center gap-2 text-sm text-slate-200">
                <input
                  type="checkbox"
                  checked={limitRunWindow}
                  onChange={(event) => setLimitRunWindow(event.target.checked)}
                />
                Limit run window (start / end)
              </label>
              <p className="text-xs text-muted leading-relaxed">{runWindowCatalogHint}</p>
              {limitRunWindow && (
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field
                    label="Start"
                    hint={`First included bar opens at or after this instant (${formatBarIntervalHint(candleMinutes)}).`}
                  >
                    <TextInput
                      type="datetime-local"
                      value={runStartLocal}
                      onChange={(event) => setRunStartLocal(event.target.value)}
                    />
                  </Field>
                  <Field
                    label="End"
                    hint={`Last included bar closes at or before this instant (${formatBarIntervalHint(candleMinutes)}).`}
                  >
                    <TextInput
                      type="datetime-local"
                      value={runEndLocal}
                      onChange={(event) => setRunEndLocal(event.target.value)}
                    />
                  </Field>
                </div>
              )}
            </div>
          </div>
        </Card>

        <JobErrorAlert error={runMutation.error} />
        <Button type="submit" disabled={!canRun || runMutation.isPending}>
          {runMutation.isPending ? "Starting…" : "Run custom pipeline"}
        </Button>
      </form>
      </div>

      <div className="lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)] lg:self-start lg:overflow-y-auto">
        <JobMonitor activeJobId={jobId} onSelectJob={setJobId} />
      </div>
    </div>
  );
}
