"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";
import { JobErrorAlert } from "@/components/JobErrorAlert";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import { api, type CatalogStrategy, type DatasetRow } from "@/lib/api";

type JobTab = "test" | "compare";

function ruleStrategies(rows: CatalogStrategy[]): CatalogStrategy[] {
  return rows.filter((row) => row.style !== "ml");
}

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

  useEffect(() => {
    const datasets = datasetsQuery.data ?? [];
    if (!compareDatasetId && datasets[0]) {
      setCompareDatasetId(datasets[0].id);
    }
    if (!testDatasetId && datasets[0]) {
      setTestDatasetId(datasets[0].id);
    }
  }, [datasetsQuery.data, compareDatasetId, testDatasetId]);

  const catalogStrategies = ruleStrategies(strategiesQuery.data ?? []);

  useEffect(() => {
    if (!catalogStrategies.some((strategy) => strategy.id === testStrategyId) && catalogStrategies[0]) {
      setTestStrategyId(catalogStrategies[0].id);
    }
  }, [catalogStrategies, testStrategyId]);

  const datasetOptions = datasetsQuery.data ?? [];

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

  const tabs: { id: JobTab; label: string }[] = [
    { id: "test", label: "Strategy test" },
    { id: "compare", label: "Strategy compare" },
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

    </div>
  );
}
