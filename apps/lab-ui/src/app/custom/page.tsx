"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { JobErrorAlert } from "@/components/JobErrorAlert";
import { ErrorState } from "@/components/ui/States";
import { JobForms } from "@/components/JobForms";
import Link from "next/link";
import { JobMonitor } from "@/components/JobMonitor";
import { OptimizedStrategyParamsBlock } from "@/components/OptimizedStrategyParamsBlock";
import {
  DEFAULT_PIPELINE_DATA_STATE,
  PipelineDataSection,
  pipelineDataSourceBlockers,
  type PipelineDataSectionState,
} from "@/components/PipelineDataSection";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import { Page } from "@/components/ui/Page";
import { PageHeader } from "@/components/ui/PageHeader";
import { StrategyMultiSelect } from "@/components/StrategyMultiSelect";
import { api } from "@/lib/api";
import {
  loadCustomResearchDraft,
  saveCustomResearchDraft,
  type StrategyPickMode,
} from "@/lib/labFormCache";
import { parseCustomResearchJobSummary } from "@/lib/customResearchLog";
import {
  datetimeLocalToUtcIso,
  formatBarIntervalHint,
  minutesFromResolution,
  utcDateToDatetimeLocal,
} from "@/lib/format";

/** Default compare start ~75% through catalog coverage so optimizer has leading train bars. */
function suggestCompareStartLocal(
  datasets: Array<{ range_start_utc?: string | null; range_end_utc?: string | null }>,
): string {
  const starts = datasets.map((row) => row.range_start_utc).filter(Boolean) as string[];
  const ends = datasets.map((row) => row.range_end_utc).filter(Boolean) as string[];
  if (starts.length === 0 || ends.length === 0) return "";
  const minStart = starts.reduce((a, b) => (a < b ? a : b)).slice(0, 10);
  const maxEnd = ends.reduce((a, b) => (a > b ? a : b)).slice(0, 10);
  const startMs = Date.parse(`${minStart}T00:00:00Z`);
  const endMs = Date.parse(`${maxEnd}T00:00:00Z`);
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) return "";
  const splitMs = startMs + (endMs - startMs) * 0.75;
  return utcDateToDatetimeLocal(new Date(splitMs).toISOString().slice(0, 10));
}

export default function CustomPipelinePage() {
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const [dataState, setDataState] = useState<PipelineDataSectionState>(DEFAULT_PIPELINE_DATA_STATE);

  const [compareStrategies, setCompareStrategies] = useState(true);
  const [maxStrategies, setMaxStrategies] = useState("");
  const [strategyPickMode, setStrategyPickMode] = useState<StrategyPickMode>("all");
  const [singleStrategyId, setSingleStrategyId] = useState("");
  const [enabledStrategyIds, setEnabledStrategyIds] = useState<Set<string>>(new Set());

  const [cash, setCash] = useState("10000");
  const [feePct, setFeePct] = useState("0.045");
  const [execution, setExecution] = useState("next_open");
  const [vectorbt, setVectorbt] = useState(true);
  const [visualize, setVisualize] = useState(true);
  const [limitRunWindow, setLimitRunWindow] = useState(false);
  const [runStartLocal, setRunStartLocal] = useState("");
  const [runEndLocal, setRunEndLocal] = useState("");
  const [useOptimizedStrategyParams, setUseOptimizedStrategyParams] = useState(true);
  const [optimizeBeforeCompare, setOptimizeBeforeCompare] = useState(false);
  const [optimizeSelectionMode, setOptimizeSelectionMode] = useState<"validation" | "in_sample">(
    "validation",
  );
  const [optimizeHoldoutBars, setOptimizeHoldoutBars] = useState("");
  const [strategyManualParams, setStrategyManualParams] = useState<Record<string, unknown>>({});
  /** Run window was turned on only because grid-search was enabled — clear it when grid-search is off. */
  const limitRunWindowAutoFromOptimize = useRef(false);
  const [formReady, setFormReady] = useState(false);
  const [draftRestored, setDraftRestored] = useState(false);

  const datasetsQuery = useQuery({ queryKey: ["datasets"], queryFn: () => api.datasets(300) });
  const strategiesQuery = useQuery({
    queryKey: ["catalog-strategies"],
    queryFn: () => api.catalogStrategies(true),
  });
  const ruleStrategies = useMemo(() => strategiesQuery.data ?? [], [strategiesQuery.data]);

  const customJobQuery = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.job(jobId!),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status ?? "";
      return status === "queued" || status === "running" ? 2000 : false;
    },
  });

  const discoveryMarketsHref = useMemo(() => {
    const symbols =
      dataState.exportMarketSymbols.length > 0
        ? dataState.exportMarketSymbols
        : dataState.exportMarketSymbol.trim()
          ? [dataState.exportMarketSymbol.trim()]
          : [];
    if (symbols.length === 0) {
      return "/new#discovery";
    }
    return `/new?markets=${encodeURIComponent(symbols.join(","))}#discovery`;
  }, [dataState.exportMarketSymbols, dataState.exportMarketSymbol]);

  const compareBenchmarks = useMemo(() => {
    if (customJobQuery.data?.status !== "completed") {
      return null;
    }
    return parseCustomResearchJobSummary(customJobQuery.data.log_text ?? "");
  }, [customJobQuery.data?.status, customJobQuery.data?.log_text]);

  useEffect(() => {
    const draft = loadCustomResearchDraft();
    if (draft) {
      setDataState(draft.dataState);
      setCompareStrategies(draft.compareStrategies);
      setMaxStrategies(draft.maxStrategies);
      setStrategyPickMode(draft.strategyPickMode);
      setSingleStrategyId(draft.singleStrategyId);
      setEnabledStrategyIds(new Set(draft.enabledStrategyIds));
      setCash(draft.cash);
      setFeePct(draft.feePct);
      setExecution(draft.execution);
      setVectorbt(draft.vectorbt);
      setVisualize(draft.visualize);
      setLimitRunWindow(draft.limitRunWindow);
      setRunStartLocal(draft.runStartLocal);
      setRunEndLocal(draft.runEndLocal);
      setUseOptimizedStrategyParams(draft.useOptimizedStrategyParams);
      setOptimizeBeforeCompare(draft.optimizeBeforeCompare);
      setOptimizeSelectionMode(draft.optimizeSelectionMode);
      setOptimizeHoldoutBars(draft.optimizeHoldoutBars);
      setStrategyManualParams(draft.strategyManualParams);
      setDraftRestored(true);
    }
    setFormReady(true);
  }, []);

  useEffect(() => {
    if (!formReady) {
      return;
    }
    const handle = window.setTimeout(() => {
      saveCustomResearchDraft({
        version: 1,
        dataState,
        compareStrategies,
        maxStrategies,
        strategyPickMode,
        singleStrategyId,
        enabledStrategyIds: [...enabledStrategyIds],
        cash,
        feePct,
        execution,
        vectorbt,
        visualize,
        limitRunWindow,
        runStartLocal,
        runEndLocal,
        useOptimizedStrategyParams,
        optimizeBeforeCompare,
        optimizeSelectionMode,
        optimizeHoldoutBars,
        strategyManualParams,
      });
    }, 400);
    return () => window.clearTimeout(handle);
  }, [
    formReady,
    dataState,
    compareStrategies,
    maxStrategies,
    strategyPickMode,
    singleStrategyId,
    enabledStrategyIds,
    cash,
    feePct,
    execution,
    vectorbt,
    visualize,
    limitRunWindow,
    runStartLocal,
    runEndLocal,
    useOptimizedStrategyParams,
    optimizeBeforeCompare,
    optimizeSelectionMode,
    optimizeHoldoutBars,
    strategyManualParams,
  ]);

  useEffect(() => {
    if (ruleStrategies.length === 0) return;
    if (strategyPickMode === "all") {
      setEnabledStrategyIds(new Set(ruleStrategies.map((row) => row.id)));
      return;
    }
    if (strategyPickMode === "one") {
      const fallback = ruleStrategies[0]?.id ?? "";
      const id =
        singleStrategyId && ruleStrategies.some((row) => row.id === singleStrategyId)
          ? singleStrategyId
          : fallback;
      if (id) {
        setEnabledStrategyIds(new Set([id]));
        if (id !== singleStrategyId) {
          setSingleStrategyId(id);
        }
      }
    }
  }, [ruleStrategies, strategyPickMode, singleStrategyId]);

  function patchDataState(patch: Partial<PipelineDataSectionState>) {
    setDataState((previous) => ({ ...previous, ...patch }));
  }

  function selectAllStrategies() {
    setStrategyPickMode("all");
  }

  function pickOneStrategy() {
    setStrategyPickMode("one");
    const first =
      enabledStrategyIds.size === 1
        ? [...enabledStrategyIds][0]
        : ruleStrategies.find((row) => enabledStrategyIds.has(row.id))?.id ?? ruleStrategies[0]?.id ?? "";
    if (first) {
      setSingleStrategyId(first);
    }
  }

  function toggleStrategy(id: string) {
    setStrategyPickMode("subset");
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

  function clearStrategySelection() {
    setStrategyPickMode("subset");
    setEnabledStrategyIds(new Set());
  }

  /** Union-add ids (used by the picker's "Select shown"), staying in subset mode. */
  function addStrategyIds(ids: string[]) {
    setStrategyPickMode("subset");
    setEnabledStrategyIds((previous) => {
      const next = new Set(previous);
      for (const id of ids) {
        next.add(id);
      }
      return next;
    });
  }

  function enterStrategySubset() {
    setStrategyPickMode("subset");
    setEnabledStrategyIds((previous) => {
      if (previous.size > 0) {
        return previous;
      }
      return new Set(ruleStrategies.map((row) => row.id));
    });
  }

  const previewStrategyId = useMemo(() => {
    for (const row of ruleStrategies) {
      if (enabledStrategyIds.has(row.id)) {
        return row.id;
      }
    }
    return ruleStrategies[0]?.id ?? "sma_cross";
  }, [ruleStrategies, enabledStrategyIds]);

  /** Human summary shown next to the pick-mode buttons. */
  const strategyPickSummary = useMemo(() => {
    if (strategyPickMode === "all") {
      return `${ruleStrategies.length} in catalog`;
    }
    if (strategyPickMode === "one") {
      const picked = ruleStrategies.find(
        (row) => row.id === (singleStrategyId || ruleStrategies[0]?.id),
      );
      return picked ? `1 selected · ${picked.name || picked.id}` : "1 selected";
    }
    return `${enabledStrategyIds.size} of ${ruleStrategies.length} selected`;
  }, [strategyPickMode, ruleStrategies, singleStrategyId, enabledStrategyIds]);

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
    if (!runStartLocal && only.range_start_utc && !optimizeBeforeCompare) {
      setRunStartLocal(utcDateToDatetimeLocal(only.range_start_utc));
    }
    if (!runEndLocal && only.range_end_utc) {
      setRunEndLocal(utcDateToDatetimeLocal(only.range_end_utc));
    }
  }, [limitRunWindow, selectedDatasets, runStartLocal, runEndLocal, optimizeBeforeCompare]);

  const runMutation = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        export_days: Number(dataState.exportDays),
        use_all_hourly_files: dataState.useAllHourly,
        dataset_ids: dataState.datasetIds,
        compare_strategies: compareStrategies,
        visualize,
        cash: Number(cash),
        fee: Number(feePct) / 100,
        execution,
        vectorbt,
        use_optimized_strategy_params: useOptimizedStrategyParams,
        optimize_before_compare: optimizeBeforeCompare,
        optimize_selection_mode: optimizeSelectionMode,
      };
      if (optimizeHoldoutBars.trim() !== "") {
        body.optimize_holdout_tail_bars = Number(optimizeHoldoutBars);
      }
      if (!useOptimizedStrategyParams && !optimizeBeforeCompare) {
        Object.assign(body, strategyManualParams);
      }
      if (dataState.exportHistoryMode === "steps") {
        if (dataState.exportSteps.trim() !== "") {
          body.export_steps = Number(dataState.exportSteps);
        }
        const stepsByInterval: Record<string, number> = {};
        for (const [interval, steps] of Object.entries(dataState.exportStepsByInterval)) {
          if (String(steps).trim() !== "") {
            stepsByInterval[interval] = Number(steps);
          }
        }
        if (Object.keys(stepsByInterval).length > 0) {
          body.export_steps_by_interval = stepsByInterval;
        }
      } else {
        const daysByInterval: Record<string, number> = {};
        for (const [interval, days] of Object.entries(dataState.exportDaysByInterval)) {
          if (String(days).trim() !== "") {
            daysByInterval[interval] = Number(days);
          }
        }
        if (Object.keys(daysByInterval).length > 0) {
          body.export_days_by_interval = daysByInterval;
        }
      }
      if (dataState.dataSourceMode === "download" && dataState.exportMarketSymbol.trim()) {
        body.export_market_symbol = dataState.exportMarketSymbol.trim();
        body.interval = dataState.exportInterval;
      }
      if (dataState.dataSourceMode === "download" && dataState.exportMarketSymbols.length > 0) {
        body.export_market_symbols = dataState.exportMarketSymbols;
        if (dataState.exportIntervals.length > 0) {
          body.export_intervals = dataState.exportIntervals;
        } else if (dataState.exportInterval) {
          body.export_intervals = [dataState.exportInterval];
        }
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
      const runStartUtc = limitRunWindow ? datetimeLocalToUtcIso(runStartLocal) : "";
      const runEndUtc = limitRunWindow ? datetimeLocalToUtcIso(runEndLocal) : "";
      if (runStartUtc && runEndUtc && Date.parse(runStartUtc) >= Date.parse(runEndUtc)) {
        throw new Error("Run window Start must be before End.");
      }
      if (limitRunWindow) {
        // Empty bounds are valid: grid-search falls back to a per-file automatic
        // walk-forward split, and a plain compare simply uses the whole file.
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

  const runBlockers = useMemo(() => {
    const items: string[] = [];
    items.push(...pipelineDataSourceBlockers(dataState));
    if (!compareStrategies) {
      items.push("Step 2 · Strategies: turn on “Run strategy compare”.");
    } else if (strategiesQuery.isLoading) {
      items.push("Step 2 · Strategies: wait for the strategy catalog to load.");
    } else if (strategiesQuery.isError) {
      items.push("Step 2 · Strategies: fix the catalog error above before running.");
    } else if (enabledStrategyIds.size === 0) {
      items.push("Step 2 · Strategies: select at least one strategy (All strategies, Pick one, or Select multiple).");
    }
    if (limitRunWindow) {
      const startUtc = datetimeLocalToUtcIso(runStartLocal);
      const endUtc = datetimeLocalToUtcIso(runEndLocal);
      if (startUtc && endUtc && Date.parse(startUtc) >= Date.parse(endUtc)) {
        items.push("Step 3 · Simulation: run window Start must be before End.");
      }
    }
    return items;
  }, [
    dataState,
    compareStrategies,
    strategiesQuery.isLoading,
    strategiesQuery.isError,
    enabledStrategyIds.size,
    limitRunWindow,
    runStartLocal,
    runEndLocal,
  ]);

  const canRun = runBlockers.length === 0;

  return (
    <Page className="space-y-6 sm:space-y-8 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(18rem,22rem)] lg:items-start lg:gap-8 lg:space-y-0">
      <div className="space-y-8 min-w-0">
      <PageHeader
        eyebrow="Pipeline Studio"
        title="Research pipeline"
        description="Configure an end-to-end run: download one or a batch of markets × horizons from Nobitex, or pick OHLC files, then compare rule-based strategies (with a cap or subset)."
      />

      {strategiesQuery.isError && (
        <ErrorState title="Could not load strategy catalog" error={strategiesQuery.error} hintAuth={false} />
      )}

      {draftRestored && (
        <p className="text-xs text-muted">
          Restored your last research settings from this browser. Changes save automatically.
        </p>
      )}

      <Card
        title="Optimizer"
        description="Optuna sweeps, batch tuning on many CSVs, Hyperliquid export pipelines, and sweep history."
      >
        <Link href="/optimizer">
          <Button variant="secondary">Open Optimizer</Button>
        </Link>
      </Card>

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
                    <div className="grid gap-2 sm:grid-cols-2">{[0, 1, 2, 3].map((index) => <div key={index} className="h-8 animate-pulse rounded-lg bg-surface" />)}</div>
                  ) : (
                    <div className="space-y-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <Button
                          type="button"
                          variant={strategyPickMode === "all" ? "primary" : "secondary"}
                          onClick={selectAllStrategies}
                          disabled={ruleStrategies.length === 0}
                        >
                          All strategies
                        </Button>
                        <Button
                          type="button"
                          variant={strategyPickMode === "one" ? "primary" : "secondary"}
                          onClick={pickOneStrategy}
                          disabled={ruleStrategies.length === 0}
                        >
                          Pick one
                        </Button>
                        <Button
                          type="button"
                          variant={strategyPickMode === "subset" ? "primary" : "secondary"}
                          onClick={enterStrategySubset}
                          disabled={ruleStrategies.length === 0}
                        >
                          Select multiple
                        </Button>
                        <span className="self-center text-xs text-muted">{strategyPickSummary}</span>
                      </div>
                      {strategyPickMode === "one" && (
                        <SelectInput
                          value={(singleStrategyId || ruleStrategies[0]?.id) ?? ""}
                          onChange={(event) => {
                            setSingleStrategyId(event.target.value);
                            setEnabledStrategyIds(new Set([event.target.value]));
                          }}
                        >
                          {ruleStrategies.map((strategy) => (
                            <option key={strategy.id} value={strategy.id}>
                              {strategy.name || strategy.id}
                            </option>
                          ))}
                        </SelectInput>
                      )}
                      {strategyPickMode === "subset" && (
                        <StrategyMultiSelect
                          strategies={ruleStrategies}
                          enabledIds={enabledStrategyIds}
                          onToggle={toggleStrategy}
                          onAddIds={addStrategyIds}
                          onClear={clearStrategySelection}
                        />
                      )}
                      {strategyPickMode === "subset" && (
                        <button
                          type="button"
                          className="text-xs text-accent hover:underline"
                          onClick={pickOneStrategy}
                        >
                          Switch to single strategy
                        </button>
                      )}
                    </div>
                  )}
                </Field>
                <label className="flex items-center gap-2 text-sm text-slate-200">
                  <input
                    type="checkbox"
                    checked={optimizeBeforeCompare}
                    onChange={(event) => {
                      const checked = event.target.checked;
                      setOptimizeBeforeCompare(checked);
                      if (checked) {
                        setUseOptimizedStrategyParams(true);
                        if (!limitRunWindow) {
                          setLimitRunWindow(true);
                          limitRunWindowAutoFromOptimize.current = true;
                        }
                        // Drop a Start that was auto-filled to the dataset's first bar: it
                        // would leave 0 leading bars and force a failure. Empty = auto split.
                        const onlyStart =
                          selectedDatasets.length === 1
                            ? selectedDatasets[0]?.range_start_utc ?? null
                            : null;
                        const autoStart = onlyStart ? utcDateToDatetimeLocal(onlyStart) : "";
                        if (autoStart && runStartLocal === autoStart) {
                          setRunStartLocal("");
                        } else if (!datetimeLocalToUtcIso(runStartLocal)) {
                          const suggested = suggestCompareStartLocal(selectedDatasets);
                          if (suggested) {
                            setRunStartLocal(suggested);
                          }
                        }
                      } else if (limitRunWindowAutoFromOptimize.current) {
                        setLimitRunWindow(false);
                        limitRunWindowAutoFromOptimize.current = false;
                      }
                    }}
                  />
                  Grid-search before compare (each market × interval × strategy; stored per symbol and resolution)
                </label>
                {optimizeBeforeCompare && (
                  <p className="text-xs text-muted leading-relaxed">
                    Optimizer uses bars <strong className="font-medium text-slate-300">before</strong> compare: an
                    inner train / validation / test split picks params (test is report-only). Compare is a separate
                    out-of-sample window. Leave run-window <strong className="font-medium text-slate-300">Start</strong>{" "}
                    empty for an automatic ~65% train / 35% compare split per file.
                  </p>
                )}
                {optimizeBeforeCompare && (
                  <Field
                    label="Optimizer selection"
                    hint="Validation is recommended; in-sample uses holdout reporting only when data is short."
                  >
                    <SelectInput
                      value={optimizeSelectionMode}
                      onChange={(event) =>
                        setOptimizeSelectionMode(event.target.value as "validation" | "in_sample")
                      }
                    >
                      <option value="validation">Train / validation / test</option>
                      <option value="in_sample">In-sample (legacy)</option>
                    </SelectInput>
                  </Field>
                )}
                {optimizeBeforeCompare && optimizeSelectionMode === "in_sample" && (
                  <Field
                    label="Optimizer holdout bars"
                    hint="Trailing bars for holdout report when using in-sample mode. Empty uses ~20% of train bars."
                  >
                    <TextInput
                      type="number"
                      min={1}
                      placeholder="e.g. 50"
                      value={optimizeHoldoutBars}
                      onChange={(event) => setOptimizeHoldoutBars(event.target.value)}
                    />
                  </Field>
                )}
                <div className="panel-inset space-y-2">
                  <p className="text-xs text-muted">
                    Preview for <span className="text-slate-300">{previewStrategyId}</span>. Compare uses robust
                    defaults when enabled; after a pre-compare sweep, winners from that run are applied.
                  </p>
                  <OptimizedStrategyParamsBlock
                    strategyId={previewStrategyId}
                    symbol={firstDataset?.symbol ?? null}
                    resolution={firstDataset?.resolution ?? null}
                    datasetId={firstDataset?.id ?? null}
                    useOptimized={useOptimizedStrategyParams}
                    onUseOptimizedChange={setUseOptimizedStrategyParams}
                    manualValues={strategyManualParams}
                    onManualValuesChange={setStrategyManualParams}
                  />
                </div>
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
              <Field label="Fee per side (%)" hint="Hyperliquid perp taker default: 0.045%.">
                <TextInput
                  type="number"
                  min={0}
                  max={100}
                  step="any"
                  value={feePct}
                  onChange={(event) => setFeePct(event.target.value)}
                />
              </Field>
            </div>
            <Field
              label="Execution"
              hint="next_open fills at the next bar open (realistic delay; last-bar signals expire). Returns are net of exchange fees."
            >
              <SelectInput value={execution} onChange={(event) => setExecution(event.target.value)}>
                <option value="close">Signal-bar close (optimistic)</option>
                <option value="next_open">Next-bar open (realistic)</option>
              </SelectInput>
            </Field>
            <label className="flex items-center gap-2 text-sm text-muted">
              <input
                type="checkbox"
                checked={vectorbt}
                onChange={(event) => setVectorbt(event.target.checked)}
              />
              Include vectorbt risk metrics on compare runs
            </label>

            <p className="text-xs leading-relaxed text-muted">
              Many strategies can show negative returns on the same window — especially with{" "}
              <span className="text-slate-300">next_open</span> fills and per-side fees. After a run,
              compare each strategy to <span className="text-slate-300">buy-and-hold</span> on the
              same bars (see job log and summary panel). If buy-and-hold is also negative, the market
              window is down; rules are not broken.
            </p>

            <div className="panel-inset space-y-3">
              <label className="flex items-center gap-2 text-sm text-slate-200">
                <input
                  type="checkbox"
                  checked={limitRunWindow}
                  onChange={(event) => {
                    const checked = event.target.checked;
                    if (!checked && optimizeBeforeCompare) {
                      setOptimizeBeforeCompare(false);
                      limitRunWindowAutoFromOptimize.current = false;
                    }
                    if (checked) {
                      limitRunWindowAutoFromOptimize.current = false;
                    }
                    setLimitRunWindow(checked);
                  }}
                />
                Limit run window (start / end)
              </label>
              {optimizeBeforeCompare && (
                <p className="text-xs text-muted">
                  Grid-search uses this window for the compare side (train bars come before it). Leave both empty for a
                  per-file automatic split; uncheck here to run on the full file (grid-search turns off).
                </p>
              )}
              <p className="text-xs text-muted leading-relaxed">{runWindowCatalogHint}</p>
              {limitRunWindow && (
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field
                    label="Start"
                    hint={`First compared bar opens at or after this instant (${formatBarIntervalHint(candleMinutes)}). Empty = automatic walk-forward split.`}
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
        {runBlockers.length > 0 && !runMutation.isPending && (
          <div
            className="rounded-lg border border-amber-500/35 bg-amber-500/10 px-4 py-3 text-sm"
            role="status"
            aria-live="polite"
          >
            <p className="font-medium text-amber-50">Complete these to run the pipeline:</p>
            <ul className="mt-2 list-disc space-y-1.5 pl-5 text-xs leading-relaxed text-amber-100/90">
              {runBlockers.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        )}
        <Button type="submit" disabled={!canRun || runMutation.isPending}>
          {runMutation.isPending ? "Starting…" : "Run custom pipeline"}
        </Button>
      </form>

      <Card
        title="Market opportunity discovery"
        description="Scan Hyperliquid perps × timeframes × strategies with walk-forward scoring. Runs on the New page with history and job monitor."
      >
        <Link href={discoveryMarketsHref}>
          <Button variant="secondary">Open discovery on New</Button>
        </Link>
      </Card>

      <section id="quick-jobs" className="scroll-mt-24">
      <Card
        title="Quick jobs"
        description="Run a single backtest, a local strategy compare, or a parameter sweep on one dataset — without the full multi-file pipeline above."
      >
        <JobForms onJob={setJobId} />
      </Card>
      </section>
      </div>

      <div className="lg:sticky lg:top-24 lg:max-h-[calc(100vh-7rem)] lg:self-start lg:space-y-4 lg:overflow-y-auto">
        {compareBenchmarks && compareBenchmarks.compare.length > 0 && (
          <Card
            title="Compare vs buy-and-hold"
            description="Same CSV window, cash, fee, and execution as the compare step."
          >
            <ul className="space-y-3 text-sm">
              {compareBenchmarks.compare.map((row) => {
                const file = row.csv.split("/").pop() ?? row.csv;
                const bench = row.buy_and_hold_return_pct;
                const best = row.best_return_pct;
                return (
                  <li
                    key={row.csv}
                    className="rounded-lg border border-border/80 bg-surface/50 px-3 py-2"
                  >
                    <div className="font-medium text-slate-200">{file}</div>
                    <dl className="mt-1 grid gap-1 text-xs text-muted">
                      <div className="flex justify-between gap-2">
                        <dt>Buy-and-hold</dt>
                        <dd className="text-slate-300">
                          {bench != null ? `${bench >= 0 ? "+" : ""}${bench.toFixed(2)}%` : "—"}
                        </dd>
                      </div>
                      <div className="flex justify-between gap-2">
                        <dt>Best strategy</dt>
                        <dd className="text-slate-300">
                          {row.best_strategy_id ?? "—"}
                          {best != null ? ` (${best >= 0 ? "+" : ""}${best.toFixed(2)}%)` : ""}
                        </dd>
                      </div>
                      {row.strategies_count != null && row.strategies_beat_buy_hold != null && (
                        <div className="flex justify-between gap-2">
                          <dt>Beat buy-and-hold</dt>
                          <dd className="text-slate-300">
                            {row.strategies_beat_buy_hold} / {row.strategies_count}
                          </dd>
                        </div>
                      )}
                    </dl>
                  </li>
                );
              })}
            </ul>
          </Card>
        )}
        <JobMonitor activeJobId={jobId} onSelectJob={setJobId} />
      </div>
    </Page>
  );
}
