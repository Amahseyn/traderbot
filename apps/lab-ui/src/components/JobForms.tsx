"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";
import { JobErrorAlert } from "@/components/JobErrorAlert";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import { api, type DatasetRow, type StrategyParamField } from "@/lib/api";

type JobTab = "test" | "compare" | "sweep";

type BacktestParamState = {
  cash: string;
  fee: string;
  vectorbt: boolean;
  fast: string;
  slow: string;
  signal: string;
  period: string;
  oversold: string;
  overbought: string;
  numStd: string;
  contextBars: string;
  priceConfirm: boolean;
};

function backtestParamsBody(params: BacktestParamState): Record<string, unknown> {
  return {
    cash: Number(params.cash),
    fee: Number(params.fee),
    vectorbt: params.vectorbt,
    fast: Number(params.fast),
    slow: Number(params.slow),
    signal: Number(params.signal),
    period: Number(params.period),
    oversold: Number(params.oversold),
    overbought: Number(params.overbought),
    num_std: Number(params.numStd),
    context_bars: Number(params.contextBars),
    price_confirm: params.priceConfirm,
  };
}

function parseSweepValues(text: string): unknown[] {
  const values: unknown[] = [];
  for (const token of text.split(",")) {
    const cleaned = token.trim();
    if (!cleaned) continue;
    const lowered = cleaned.toLowerCase();
    if (lowered === "true" || lowered === "false") {
      values.push(lowered === "true");
      continue;
    }
    const numeric = Number(cleaned);
    values.push(Number.isNaN(numeric) ? cleaned : numeric);
  }
  return values;
}

function prettyParamLabel(name: string): string {
  return name.replaceAll("_", " ");
}

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

const DEFAULT_BACKTEST_PARAMS: BacktestParamState = {
  cash: "10000",
  fee: "0",
  vectorbt: false,
  fast: "5",
  slow: "20",
  signal: "9",
  period: "14",
  oversold: "30",
  overbought: "70",
  numStd: "2",
  contextBars: "0",
  priceConfirm: false,
};

function BacktestSimulationFields({
  params,
  onChange,
  showStrategyParams,
  onToggleStrategyParams,
}: {
  params: BacktestParamState;
  onChange: (patch: Partial<BacktestParamState>) => void;
  showStrategyParams: boolean;
  onToggleStrategyParams: () => void;
}) {
  return (
    <section className="panel-inset space-y-3">
      <h3 className="text-sm font-medium text-white">Simulation</h3>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Starting cash">
          <TextInput
            type="number"
            min={1}
            step={100}
            value={params.cash}
            onChange={(event) => onChange({ cash: event.target.value })}
          />
        </Field>
        <Field label="Fee per trade" hint="Fraction of trade value, e.g. 0.001 = 0.1%.">
          <TextInput
            type="number"
            min={0}
            step={0.0001}
            value={params.fee}
            onChange={(event) => onChange({ fee: event.target.value })}
          />
        </Field>
      </div>
      <label className="flex items-center gap-2 text-sm text-muted">
        <input
          type="checkbox"
          checked={params.vectorbt}
          onChange={(event) => onChange({ vectorbt: event.target.checked })}
        />
        Include vectorbt metrics when available
      </label>
      <button
        type="button"
        className="text-sm text-accent hover:underline"
        onClick={onToggleStrategyParams}
      >
        {showStrategyParams ? "Hide strategy parameters" : "Strategy parameters (windows, bands, context)"}
      </button>
      {showStrategyParams && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Fast window">
            <TextInput
              type="number"
              min={1}
              value={params.fast}
              onChange={(event) => onChange({ fast: event.target.value })}
            />
          </Field>
          <Field label="Slow window">
            <TextInput
              type="number"
              min={1}
              value={params.slow}
              onChange={(event) => onChange({ slow: event.target.value })}
            />
          </Field>
          <Field label="MACD signal">
            <TextInput
              type="number"
              min={1}
              value={params.signal}
              onChange={(event) => onChange({ signal: event.target.value })}
            />
          </Field>
          <Field label="RSI period">
            <TextInput
              type="number"
              min={1}
              value={params.period}
              onChange={(event) => onChange({ period: event.target.value })}
            />
          </Field>
          <Field label="RSI oversold">
            <TextInput
              type="number"
              value={params.oversold}
              onChange={(event) => onChange({ oversold: event.target.value })}
            />
          </Field>
          <Field label="RSI overbought">
            <TextInput
              type="number"
              value={params.overbought}
              onChange={(event) => onChange({ overbought: event.target.value })}
            />
          </Field>
          <Field label="Bollinger σ">
            <TextInput
              type="number"
              min={0.1}
              step={0.1}
              value={params.numStd}
              onChange={(event) => onChange({ numStd: event.target.value })}
            />
          </Field>
          <Field
            label="Recent-price context"
            hint="Bars for mean-reversion filters. 0 keeps legacy behavior."
          >
            <TextInput
              type="number"
              min={0}
              value={params.contextBars}
              onChange={(event) => onChange({ contextBars: event.target.value })}
            />
          </Field>
          <div className="sm:col-span-2">
            <label className="flex items-center gap-2 text-sm text-muted">
              <input
                type="checkbox"
                checked={params.priceConfirm}
                onChange={(event) => onChange({ priceConfirm: event.target.checked })}
              />
              Trend strategies: require close on the fast average side before entry
            </label>
          </div>
        </div>
      )}
    </section>
  );
}

function EmptyDatasets({ failed = false }: { failed?: boolean }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted">
        {failed
          ? "The dataset list did not load. Start ./run-lab.sh (or ./run-lab-api.sh) and refresh."
          : "No price files in the catalog yet. Export OHLC on Data, then pick that file here."}
      </p>
      {!failed && (
        <Link
          href="/data"
          className="inline-flex items-center justify-center rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white transition hover:bg-blue-500"
        >
          Go to Data
        </Link>
      )}
    </div>
  );
}

export function JobForms({ onJob }: { onJob: (jobId: string) => void }) {
  const [tab, setTab] = useState<JobTab>("test");

  const datasetsQuery = useQuery({ queryKey: ["datasets"], queryFn: () => api.datasets() });
  const strategiesQuery = useQuery({
    queryKey: ["catalog-strategies"],
    queryFn: () => api.catalogStrategies(true),
  });

  const [compareDatasetId, setCompareDatasetId] = useState("");
  const [compareVisualize, setCompareVisualize] = useState(true);
  const [compareParams, setCompareParams] = useState<BacktestParamState>(DEFAULT_BACKTEST_PARAMS);
  const [compareShowParams, setCompareShowParams] = useState(false);

  const [testDatasetId, setTestDatasetId] = useState("");
  const [testVisualize, setTestVisualize] = useState(true);
  const [testStrategyId, setTestStrategyId] = useState("");

  const [sweepDatasetId, setSweepDatasetId] = useState("");
  const [sweepStrategyId, setSweepStrategyId] = useState("");
  const [sweepParamA, setSweepParamA] = useState("fast");
  const [sweepValuesA, setSweepValuesA] = useState("5, 10, 20");
  const [sweepUseSecondParam, setSweepUseSecondParam] = useState(true);
  const [sweepParamB, setSweepParamB] = useState("slow");
  const [sweepValuesB, setSweepValuesB] = useState("20, 50");
  const [sweepCash, setSweepCash] = useState("10000");
  const [sweepFee, setSweepFee] = useState("0");
  const [sweepHoldout, setSweepHoldout] = useState("");
  const [sweepMinTrades, setSweepMinTrades] = useState("0");
  const [sweepMaxCombos, setSweepMaxCombos] = useState("64");
  const [sweepBase, setSweepBase] = useState<Record<string, unknown>>({});
  const [sweepBaseFor, setSweepBaseFor] = useState("");
  const [showSweepBase, setShowSweepBase] = useState(false);

  useEffect(() => {
    const datasets = datasetsQuery.data ?? [];
    if (!compareDatasetId && datasets[0]) {
      setCompareDatasetId(datasets[0].id);
    }
    if (!testDatasetId && datasets[0]) {
      setTestDatasetId(datasets[0].id);
    }
    if (!sweepDatasetId && datasets[0]) {
      setSweepDatasetId(datasets[0].id);
    }
  }, [datasetsQuery.data, compareDatasetId, testDatasetId, sweepDatasetId]);

  const catalogStrategies = strategiesQuery.data ?? [];

  useEffect(() => {
    if (!catalogStrategies.some((strategy) => strategy.id === testStrategyId) && catalogStrategies[0]) {
      setTestStrategyId(catalogStrategies[0].id);
    }
    if (!catalogStrategies.some((strategy) => strategy.id === sweepStrategyId) && catalogStrategies[0]) {
      setSweepStrategyId(catalogStrategies[0].id);
    }
  }, [catalogStrategies, testStrategyId, sweepStrategyId]);

  const datasetOptions = datasetsQuery.data ?? [];

  const sweepDataset = datasetOptions.find((dataset) => dataset.id === sweepDatasetId);
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
  const sweepParamFields = strategyParamsQuery.data?.params ?? [];
  const sweepParamNames = sweepParamFields.map((field) => field.name);

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
  }, [strategyParamsQuery.data, sweepParamA, sweepParamB]);

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

  const compareMutation = useMutation({
    mutationFn: () =>
      api.postJob("strategy-compare", {
        dataset_id: compareDatasetId,
        visualize: compareVisualize,
        mode: "strategies",
        ...backtestParamsBody(compareParams),
      }),
    onSuccess: (data) => onJob(data.id),
  });

  const testMutation = useMutation({
    mutationFn: () =>
      api.postJob("strategy-test", {
        dataset_id: testDatasetId,
        visualize: testVisualize,
        mode: "strategies",
        strategy_id: testStrategyId,
      }),
    onSuccess: (data) => onJob(data.id),
  });

  const sweepValuesPreviewA = parseSweepValues(sweepValuesA);
  const sweepValuesPreviewB = parseSweepValues(sweepValuesB);
  const sweepMutation = useMutation({
    mutationFn: () => {
      const params: Record<string, unknown[]> = { [sweepParamA]: parseSweepValues(sweepValuesA) };
      if (sweepUseSecondParam && sweepParamB && sweepParamB !== sweepParamA) {
        const second = parseSweepValues(sweepValuesB);
        if (second.length > 0) params[sweepParamB] = second;
      }
      return api.postJob("strategy-sweep", {
        dataset_id: sweepDatasetId,
        mode: "strategies",
        strategy_id: sweepStrategyId,
        params,
        ...sweepBase,
        cash: Number(sweepCash),
        fee: Number(sweepFee),
        holdout_tail_bars: sweepHoldout === "" ? null : Number(sweepHoldout),
        min_trades: Number(sweepMinTrades),
        max_combos: Number(sweepMaxCombos),
      });
    },
    onSuccess: (data) => onJob(data.id),
  });
  const sweepReady =
    Boolean(sweepDatasetId) &&
    Boolean(sweepStrategyId) &&
    sweepValuesPreviewA.length > 0 &&
    (!sweepUseSecondParam || sweepValuesPreviewB.length > 0);

  const tabs: { id: JobTab; label: string }[] = [
    { id: "test", label: "Strategy test" },
    { id: "compare", label: "Strategy compare" },
    { id: "sweep", label: "Optimizer" },
  ];

  return (
    <div className="space-y-4">
          <div className="tab-list">
            {tabs.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`tab ${tab === item.id ? "tab-active" : ""}`}
                onClick={() => setTab(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>

          {tab === "test" && (
            <Card
              title="Strategy test"
              description="Backtest one rule-based strategy on a catalog dataset."
            >
              {datasetsQuery.isLoading ? (
                <p className="text-sm text-muted">Loading datasets…</p>
              ) : datasetOptions.length === 0 ? (
                <EmptyDatasets failed={datasetsQuery.isError} />
              ) : (
                <form
                  className="space-y-4"
                  onSubmit={(event) => {
                    event.preventDefault();
                    testMutation.mutate();
                  }}
                >
                  <Field label="Dataset">
                    <SelectInput value={testDatasetId} onChange={(event) => setTestDatasetId(event.target.value)}>
                      {datasetOptions.map((dataset) => (
                        <option key={dataset.id} value={dataset.id}>
                          {dataset.label}
                        </option>
                      ))}
                    </SelectInput>
                  </Field>
                  <Field label="Strategy">
                    <SelectInput
                      value={testStrategyId}
                      onChange={(event) => setTestStrategyId(event.target.value)}
                    >
                      {catalogStrategies.map((strategy) => (
                        <option key={strategy.id} value={strategy.id}>
                          {strategy.name || strategy.id}
                        </option>
                      ))}
                    </SelectInput>
                  </Field>
                  <label className="flex items-center gap-2 text-sm text-muted">
                    <input
                      type="checkbox"
                      checked={testVisualize}
                      onChange={(event) => setTestVisualize(event.target.checked)}
                    />
                    Save charts (open the run on Runs)
                  </label>
                  <JobErrorAlert error={testMutation.error} />
                  <Button
                    type="submit"
                    disabled={testMutation.isPending || !testDatasetId || !testStrategyId}
                  >
                    Start test
                  </Button>
                </form>
              )}
            </Card>
          )}

          {tab === "compare" && (
            <Card
              title="Strategy compare"
              description="Rank every rule-based strategy on one catalog dataset."
            >
              {datasetsQuery.isLoading ? (
                <p className="text-sm text-muted">Loading datasets…</p>
              ) : datasetOptions.length === 0 ? (
                <EmptyDatasets failed={datasetsQuery.isError} />
              ) : (
              <form
                className="space-y-4"
                onSubmit={(event) => {
                  event.preventDefault();
                  compareMutation.mutate();
                }}
              >
                <Field label="Dataset">
                  <SelectInput
                    value={compareDatasetId}
                    onChange={(e) => setCompareDatasetId(e.target.value)}
                  >
                    {datasetOptions.map((dataset) => (
                      <option key={dataset.id} value={dataset.id}>
                        {dataset.label}
                      </option>
                    ))}
                  </SelectInput>
                </Field>
                {catalogStrategies.length > 0 && (
                  <p className="text-sm text-muted">
                    Strategies: {catalogStrategies.map((strategy) => strategy.name || strategy.id).join(", ")}
                  </p>
                )}
                <BacktestSimulationFields
                  params={compareParams}
                  onChange={(patch) => setCompareParams((current) => ({ ...current, ...patch }))}
                  showStrategyParams={compareShowParams}
                  onToggleStrategyParams={() => setCompareShowParams((open) => !open)}
                />
                <label className="flex items-center gap-2 text-sm text-muted">
                  <input
                    type="checkbox"
                    checked={compareVisualize}
                    onChange={(e) => setCompareVisualize(e.target.checked)}
                  />
                  Save ranking charts (they show under Compare results)
                </label>
                <JobErrorAlert error={compareMutation.error} />
                <Button
                  type="submit"
                  disabled={compareMutation.isPending || !compareDatasetId}
                >
                  Start compare
                </Button>
              </form>
              )}
            </Card>
          )}

          {tab === "sweep" && (
            <Card
              title="Optimizer"
              description="Grid-search 1–2 parameters for one strategy, ranked by holdout tail or full return. The grid and base knobs follow the selected strategy."
            >
              {datasetsQuery.isLoading ? (
                <p className="text-sm text-muted">Loading datasets…</p>
              ) : datasetOptions.length === 0 ? (
                <EmptyDatasets failed={datasetsQuery.isError} />
              ) : (
              <form
                className="space-y-4"
                onSubmit={(event) => {
                  event.preventDefault();
                  sweepMutation.mutate();
                }}
              >
                <Field label="Dataset">
                  <SelectInput
                    value={sweepDatasetId}
                    onChange={(event) => setSweepDatasetId(event.target.value)}
                  >
                    {datasetOptions.map((dataset) => (
                      <option key={dataset.id} value={dataset.id}>
                        {dataset.label}
                      </option>
                    ))}
                  </SelectInput>
                </Field>
                <Field label="Strategy">
                  <SelectInput
                    value={sweepStrategyId}
                    onChange={(event) => setSweepStrategyId(event.target.value)}
                  >
                    {catalogStrategies.map((strategy) => (
                      <option key={strategy.id} value={strategy.id}>
                        {strategy.name || strategy.id}
                      </option>
                    ))}
                  </SelectInput>
                </Field>
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
                        {sweepParamNames.filter((name) => name !== sweepParamA).map((name) => (
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
                <button
                  type="button"
                  className="text-sm text-accent hover:underline"
                  onClick={() => setShowSweepBase((open) => !open)}
                >
                  {showSweepBase
                    ? "Hide base strategy parameters"
                    : "Base strategy parameters (used for every knob outside the grid)"}
                </button>
                {showSweepBase && (
                  strategyParamsQuery.isLoading ? (
                    <p className="text-sm text-muted">Loading parameters…</p>
                  ) : (
                    <SweepBaseParamsFields
                      fields={sweepParamFields}
                      values={sweepBase}
                      onChange={(name, value) =>
                        setSweepBase((current) => ({ ...current, [name]: value }))
                      }
                    />
                  )
                )}
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Starting cash">
                    <TextInput
                      type="number"
                      min={1}
                      value={sweepCash}
                      onChange={(event) => setSweepCash(event.target.value)}
                    />
                  </Field>
                  <Field label="Fee per trade" hint="Fraction, e.g. 0.001 = 0.1%.">
                    <TextInput
                      type="number"
                      min={0}
                      step={0.0001}
                      value={sweepFee}
                      onChange={(event) => setSweepFee(event.target.value)}
                    />
                  </Field>
                  <Field label="Holdout bars" hint="Rank by the last N bars. Empty = full return.">
                    <TextInput
                      type="number"
                      min={1}
                      value={sweepHoldout}
                      onChange={(event) => setSweepHoldout(event.target.value)}
                      placeholder="e.g. 50"
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
                <Button
                  type="submit"
                  disabled={sweepMutation.isPending || !sweepReady}
                >
                  Start sweep
                </Button>
              </form>
              )}
            </Card>
          )}

    </div>
  );
}
