"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { JobErrorAlert } from "@/components/JobErrorAlert";
import { MarketSearchPicker } from "@/components/MarketSearchPicker";
import { OptimizedStrategyParamsBlock } from "@/components/OptimizedStrategyParamsBlock";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import { api, type MarketSpec } from "@/lib/api";
import { formatDurationMinutes, formatResolutionLabel, minutesFromResolution } from "@/lib/format";

type ExecutionMode = "once" | "continuous";
type OrderMode = "paper" | "live";
type ContinuousLimit = "until_stopped" | "max_cycles";

const MAX_LIVE_BATCH_COMBOS = 16;

type BatchMarket = {
  symbol: string;
  src: string;
  dst: string;
  label: string;
};

export type LiveSessionConfig = {
  src: string;
  dst: string;
  interval: string;
  marketSymbol: string | null;
};

type LiveTradingPanelProps = {
  onJobsStarted: (jobIds: string[]) => void;
  onSessionChange?: (config: LiveSessionConfig) => void;
};

function defaultPaperCash(dst: string): string {
  return dst.trim().toLowerCase() === "usdt" ? "1000" : "10000000";
}

function SegmentedOption<T extends string>({
  value,
  options,
  onChange,
  disabled,
}: {
  value: T;
  options: Array<{ id: T; label: string; description?: string }>;
  onChange: (id: T) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
      {options.map((option) => {
        const active = value === option.id;
        return (
          <button
            key={option.id}
            type="button"
            disabled={disabled}
            className={`min-w-[10rem] flex-1 rounded-xl border px-4 py-3 text-left transition disabled:cursor-not-allowed disabled:opacity-50 ${
              active
                ? "border-accent/60 bg-accent/15 ring-1 ring-accent/30"
                : "border-border bg-surface text-slate-300 hover:border-slate-600"
            }`}
            onClick={() => onChange(option.id)}
          >
            <span className={`block text-sm font-medium ${active ? "text-white" : ""}`}>
              {option.label}
            </span>
            {option.description && (
              <span className="mt-1 block text-xs leading-snug text-muted">{option.description}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function LiveTradingPanel({ onJobsStarted, onSessionChange }: LiveTradingPanelProps) {
  const queryClient = useQueryClient();
  const [executionMode, setExecutionMode] = useState<ExecutionMode>("once");
  const [multiRun, setMultiRun] = useState(false);
  const [batchMarkets, setBatchMarkets] = useState<BatchMarket[]>([]);
  const [batchIntervals, setBatchIntervals] = useState<string[]>([]);
  const [orderMode, setOrderMode] = useState<OrderMode>("paper");
  const [strategyId, setStrategyId] = useState("sma_cross");
  const [marketSymbol, setMarketSymbol] = useState<string | null>("BTCIRT");
  const [src, setSrc] = useState("btc");
  const [dst, setDst] = useState("rls");
  const [interval, setInterval] = useState("60");
  const [noBuy, setNoBuy] = useState(false);
  const [noSell, setNoSell] = useState(false);
  const [emitHolds, setEmitHolds] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [pollSec, setPollSec] = useState("60");
  const [continuousLimit, setContinuousLimit] = useState<ContinuousLimit>("until_stopped");
  const [maxSteps, setMaxSteps] = useState("24");
  const [useOptimized, setUseOptimized] = useState(true);
  const [strategyParams, setStrategyParams] = useState<Record<string, unknown>>({});
  const [paperInitialCash, setPaperInitialCash] = useState("10000000");

  const terminalCatalogQuery = useQuery({
    queryKey: ["catalog-terminal"],
    queryFn: () => api.catalogTerminal(true),
  });
  const authQuery = useQuery({ queryKey: ["auth-status"], queryFn: api.authStatus });

  const strategies = terminalCatalogQuery.data?.strategies ?? [];
  const resolutions = terminalCatalogQuery.data?.udf_resolutions ?? ["60", "240", "D"];

  const intervalMinutes = minutesFromResolution(interval);
  const suggestedPollSec = intervalMinutes != null ? String(Math.max(15, intervalMinutes * 60)) : "60";

  useEffect(() => {
    if (strategies.length === 0) {
      return;
    }
    if (!strategies.some((row) => row.id === strategyId)) {
      setStrategyId(strategies[0].id);
    }
  }, [strategies, strategyId]);

  useEffect(() => {
    if (executionMode === "continuous") {
      setPollSec(suggestedPollSec);
    }
  }, [executionMode, suggestedPollSec]);

  function selectMarket(market: MarketSpec) {
    setMarketSymbol(market.symbol);
    setSrc(market.src);
    setDst(market.dst);
    setPaperInitialCash(defaultPaperCash(market.dst));
  }

  function toggleBatchMarket(market: MarketSpec) {
    setBatchMarkets((rows) => {
      if (rows.some((row) => row.symbol === market.symbol)) {
        return rows.filter((row) => row.symbol !== market.symbol);
      }
      if (rows.length >= MAX_LIVE_BATCH_COMBOS) {
        return rows;
      }
      return [
        ...rows,
        {
          symbol: market.symbol,
          src: market.src.trim().toLowerCase(),
          dst: market.dst.trim().toLowerCase(),
          label: market.label,
        },
      ];
    });
  }

  function clearBatchMarkets() {
    setBatchMarkets([]);
  }

  function toggleBatchInterval(resolution: string) {
    setBatchIntervals((rows) =>
      rows.includes(resolution) ? rows.filter((item) => item !== resolution) : [...rows, resolution],
    );
  }

  const liveRunCombos = useMemo(() => {
    if (!multiRun) {
      return [
        {
          src: src.trim().toLowerCase(),
          dst: dst.trim().toLowerCase(),
          interval,
          symbol: marketSymbol ?? "",
        },
      ];
    }
    const markets = batchMarkets;
    const intervals = batchIntervals.length > 0 ? batchIntervals : [interval];
    const combos: Array<{ src: string; dst: string; interval: string; symbol: string }> = [];
    for (const market of markets) {
      for (const resolution of intervals) {
        combos.push({
          src: market.src,
          dst: market.dst,
          interval: resolution,
          symbol: market.symbol,
        });
      }
    }
    return combos;
  }, [multiRun, batchMarkets, batchIntervals, marketSymbol, src, dst, interval]);

  useEffect(() => {
    onSessionChange?.({
      src,
      dst,
      interval,
      marketSymbol,
    });
  }, [src, dst, interval, marketSymbol, onSessionChange]);

  const liveOrders = orderMode === "live";

  const jobBody = useMemo(() => {
    const body: Record<string, unknown> = {
      strategy: strategyId,
      src: src.trim().toLowerCase(),
      dst: dst.trim().toLowerCase(),
      interval,
      market_symbol: marketSymbol,
      live: liveOrders,
      no_buy: noBuy,
      no_sell: noSell,
      emit_holds: emitHolds,
      use_optimized_defaults: useOptimized,
    };
    if (!liveOrders) {
      const cash = Number(paperInitialCash);
      if (Number.isFinite(cash) && cash > 0) {
        body.paper_initial_cash = cash;
      }
    }
    if (!useOptimized) {
      Object.assign(body, strategyParams);
    }
    if (executionMode === "continuous") {
      body.poll_sec = Number(pollSec);
      if (continuousLimit === "until_stopped") {
        body.until_stopped = true;
      } else {
        body.max_steps = Number(maxSteps);
      }
    }
    return body;
  }, [
    strategyId,
    marketSymbol,
    src,
    dst,
    interval,
    liveOrders,
    paperInitialCash,
    noBuy,
    noSell,
    emitHolds,
    useOptimized,
    strategyParams,
    executionMode,
    pollSec,
    continuousLimit,
    maxSteps,
  ]);

  const submitMutation = useMutation({
    mutationFn: async () => {
      if (liveOrders && !authQuery.data?.api_keys_configured) {
        throw new Error("Configure Nobitex API keys in Settings before live orders.");
      }
      if (executionMode === "continuous" && continuousLimit === "max_cycles") {
        const steps = Number(maxSteps);
        if (!Number.isFinite(steps) || steps < 1) {
          throw new Error("Enter at least one cycle.");
        }
      }
      const poll = Number(pollSec);
      if (executionMode === "continuous" && (!Number.isFinite(poll) || poll < 5)) {
        throw new Error("Poll interval must be at least 5 seconds.");
      }
      if (liveRunCombos.length === 0) {
        throw new Error(
          multiRun
            ? "Select at least one market with the batch checkboxes below."
            : "Pick a market before starting.",
        );
      }
      if (liveRunCombos.length > MAX_LIVE_BATCH_COMBOS) {
        throw new Error(
          `Too many combinations (${liveRunCombos.length}). Limit is ${MAX_LIVE_BATCH_COMBOS} (markets × horizons).`,
        );
      }
      const jobType = executionMode === "once" ? "terminal-once" : "terminal-live";
      const started: Array<{ id: string; status: string }> = [];
      for (const combo of liveRunCombos) {
        const body = {
          ...jobBody,
          src: combo.src,
          dst: combo.dst,
          interval: combo.interval,
          market_symbol: combo.symbol,
        };
        started.push(await api.postJob(jobType, body));
      }
      return started;
    },
    onSuccess: (jobs) => {
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      if (jobs.length > 0) {
        onJobsStarted(jobs.map((job) => job.id));
      }
    },
  });

  const apiKeysReady = authQuery.data?.api_keys_configured === true;
  const pairLabel = `${src.toUpperCase()}/${dst.toUpperCase()}`;

  const comboCount = liveRunCombos.length;
  const startLabel =
    comboCount > 1
      ? executionMode === "once"
        ? `Run ${comboCount} single checks`
        : continuousLimit === "until_stopped"
          ? `Start ${comboCount} sessions`
          : `Start ${comboCount} polling jobs`
      : executionMode === "once"
        ? "Run single check"
        : continuousLimit === "until_stopped"
          ? "Start continuous session"
          : "Start polling job";

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.65fr)]">
      <div className="space-y-4">
        <Card
          title="How it works"
          description="Strategies read the latest closed Nobitex candle for your market and resolution."
        >
          <dl className="space-y-4 text-sm">
            <div>
              <dt className="font-medium text-white">Single check</dt>
              <dd className="mt-1 text-muted leading-relaxed">
                Fetches once, evaluates the strategy, prints a JSON signal (buy, sell, or hold), then
                the job ends. Use this to verify parameters before leaving a session running.
              </dd>
            </div>
            <div>
              <dt className="font-medium text-white">Continuous polling</dt>
              <dd className="mt-1 text-muted leading-relaxed">
                Repeats on a timer: wait → fetch candles → evaluate the strategy. Each poll writes a
                JSON <code className="text-slate-400">tick</code> line (including{" "}
                <code className="text-slate-400">no_new_bar</code> when the latest 1m/1h candle has
                not advanced). Buy/sell lines appear when the strategy trades; enable “Log hold signals”
                for explicit hold events. Use Stop in the job log to end a session that runs until
                stopped.
              </dd>
            </div>
            <div className="rounded-lg border border-border bg-surface/80 px-3 py-2 text-xs text-muted">
              Jobs run on the machine hosting the Lab API (same as{" "}
              <code className="text-slate-300">python -m cli terminal</code>).
            </div>
          </dl>
        </Card>

        <Card title="Credentials">
          <ul className="space-y-2 text-sm">
            <li className="flex items-center justify-between gap-2">
              <span className="text-muted">Nobitex API keys</span>
              <span className={apiKeysReady ? "text-emerald-300" : "text-amber-200"}>
                {apiKeysReady ? "Ready" : "Not set"}
              </span>
            </li>
            <li className="text-xs text-muted">
              Paper mode works without keys. Live orders need keys in{" "}
              <Link href="/settings" className="text-accent hover:underline">Settings</Link>.
            </li>
          </ul>
        </Card>
      </div>

      <Card
        title="Configure session"
        description="Pick market, strategy, and whether to trade on Nobitex or log signals only."
      >
        <div className="space-y-6">
          <div>
            <h3 className="mb-2 text-sm font-medium text-white">When to run</h3>
            <SegmentedOption
              value={executionMode}
              onChange={setExecutionMode}
              options={[
                {
                  id: "once",
                  label: "Single check",
                  description: "One fetch and one signal, then done.",
                },
                {
                  id: "continuous",
                  label: "Continuous polling",
                  description: "Timer loop until max cycles or you stop the job.",
                },
              ]}
            />
          </div>

          <div>
            <h3 className="mb-2 text-sm font-medium text-white">Trading mode</h3>
            <SegmentedOption
              value={orderMode}
              onChange={setOrderMode}
              options={[
                {
                  id: "paper",
                  label: "Paper test",
                  description: "Simulated wallet + signals — no real orders.",
                },
                {
                  id: "live",
                  label: "Live",
                  description: "Market orders on Nobitex (full wallet size).",
                },
              ]}
            />
            {orderMode === "live" && (
              <p className="mt-3 rounded-lg border border-red-500/30 bg-red-950/30 px-3 py-2 text-sm text-red-200/90">
                Live mode uses market orders and full balances. Start with paper, or enable “Ignore
                buys” under advanced options while you validate signals.
              </p>
            )}
            {orderMode === "paper" && (
              <div className="mt-3">
                <Field
                  label="Sample starting cash"
                  hint={
                    dst === "usdt"
                      ? "Paper USDT balance (default 1,000)."
                      : "Paper RLS balance (default 10,000,000)."
                  }
                >
                  <TextInput
                    type="number"
                    min={1}
                    step={1}
                    className="max-w-xs"
                    value={paperInitialCash}
                    onChange={(event) => setPaperInitialCash(event.target.value)}
                  />
                </Field>
              </div>
            )}
          </div>

          <div className="grid gap-4 border-t border-border pt-6 sm:grid-cols-2">
            <Field label="Strategy">
              <SelectInput
                value={strategyId}
                onChange={(event) => setStrategyId(event.target.value)}
              >
                {strategies.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.name || row.id}
                  </option>
                ))}
              </SelectInput>
            </Field>

            <Field label="Candle size">
              <SelectInput value={interval} onChange={(event) => setInterval(event.target.value)}>
                {resolutions.map((value) => (
                  <option key={value} value={value}>
                    {value} — {formatResolutionLabel(value)}
                  </option>
                ))}
              </SelectInput>
            </Field>
          </div>

          <div>
            <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="text-sm font-medium text-white">Market</h3>
              {marketSymbol && (
                <span className="font-mono text-xs text-muted">
                  {marketSymbol} · {pairLabel}
                </span>
              )}
            </div>
            <label className="mb-3 flex cursor-pointer items-center gap-2 text-sm text-slate-200">
              <input
                type="checkbox"
                checked={multiRun}
                onChange={(event) => {
                  const enabled = event.target.checked;
                  setMultiRun(enabled);
                  if (!enabled) {
                    setBatchMarkets([]);
                    setBatchIntervals([]);
                    return;
                  }
                  if (marketSymbol) {
                    const entry: BatchMarket = {
                      symbol: marketSymbol,
                      src: src.trim().toLowerCase(),
                      dst: dst.trim().toLowerCase(),
                      label: marketSymbol,
                    };
                    setBatchMarkets((rows) =>
                      rows.some((row) => row.symbol === entry.symbol) ? rows : [entry],
                    );
                  }
                }}
              />
              Multi run — tick several markets and/or horizons (one job per combination)
            </label>
            <MarketSearchPicker
              selectedSymbol={marketSymbol}
              onSelect={selectMarket}
              batchMode={multiRun}
              batchSymbols={batchMarkets.map((row) => row.symbol)}
              onToggleBatch={toggleBatchMarket}
              onClearBatch={clearBatchMarkets}
              maxBatchSelect={MAX_LIVE_BATCH_COMBOS}
            />
            {multiRun && (
              <div className="mt-4 space-y-2 rounded-xl border border-border bg-surface/50 p-4">
                <p className="text-xs font-medium text-slate-300">Horizons in this batch</p>
                <div className="flex flex-wrap gap-2">
                  {resolutions.map((resolution) => {
                    const checked = batchIntervals.includes(resolution);
                    return (
                      <label
                        key={resolution}
                        className={`flex cursor-pointer items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs ${
                          checked
                            ? "border-accent bg-accent/10 text-white"
                            : "border-border text-muted"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleBatchInterval(resolution)}
                        />
                        {resolution} — {formatResolutionLabel(resolution)}
                      </label>
                    );
                  })}
                </div>
                <p className="text-xs text-muted">
                  {batchMarkets.length === 0
                    ? "No markets in batch yet — use the checkboxes in the table above."
                    : `Ready to start ${comboCount} job${comboCount === 1 ? "" : "s"}`}
                  {batchIntervals.length === 0
                    ? ` (candle size: ${formatResolutionLabel(interval)} for every market).`
                    : "."}
                  {comboCount > MAX_LIVE_BATCH_COMBOS &&
                    ` Too many combinations — remove markets or horizons (max ${MAX_LIVE_BATCH_COMBOS}).`}
                </p>
              </div>
            )}
          </div>

          {executionMode === "continuous" && (
            <div className="space-y-4 rounded-xl border border-border bg-surface/50 p-4">
              <h3 className="text-sm font-medium text-white">Polling schedule</h3>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field
                  label="Wait between checks (seconds)"
                  hint={`Often set near one candle (${suggestedPollSec}s for this resolution). Minimum 5.`}
                >
                  <TextInput
                    type="number"
                    min={5}
                    step={1}
                    value={pollSec}
                    onChange={(event) => setPollSec(event.target.value)}
                  />
                </Field>
                <Field label="How long to run">
                  <SelectInput
                    value={continuousLimit}
                    onChange={(event) =>
                      setContinuousLimit(event.target.value as ContinuousLimit)
                    }
                  >
                    <option value="until_stopped">Until you click Stop</option>
                    <option value="max_cycles">Fixed number of cycles</option>
                  </SelectInput>
                </Field>
              </div>
              {continuousLimit === "max_cycles" && (
                <Field
                  label="Number of cycles"
                  hint="Each cycle fetches data and may emit one signal."
                >
                  <TextInput
                    type="number"
                    min={1}
                    step={1}
                    className="max-w-xs"
                    value={maxSteps}
                    onChange={(event) => setMaxSteps(event.target.value)}
                  />
                </Field>
              )}
              {intervalMinutes != null && (
                <p className="text-xs text-muted">
                  Candle period: {formatDurationMinutes(intervalMinutes)}. Polling does not need to
                  match candle length, but checking too often only repeats the same closed bar.
                </p>
              )}
            </div>
          )}

          <div className="space-y-2 border-t border-border pt-6">
            <h3 className="text-sm font-medium text-white">Strategy parameters</h3>
            <OptimizedStrategyParamsBlock
              strategyId={strategyId}
              symbol={marketSymbol}
              resolution={interval}
              useOptimized={useOptimized}
              onUseOptimizedChange={setUseOptimized}
              manualValues={strategyParams}
              onManualValuesChange={setStrategyParams}
            />
          </div>

          <div className="border-t border-border pt-4">
            <button
              type="button"
              className="flex w-full items-center justify-between text-sm font-medium text-slate-200 hover:text-white"
              onClick={() => setShowAdvanced((open) => !open)}
            >
              Advanced signal controls
              <span className="text-muted">{showAdvanced ? "Hide" : "Show"}</span>
            </button>
            {showAdvanced && (
              <div className="mt-3 flex flex-col gap-3 text-sm text-slate-200 sm:flex-row sm:flex-wrap">
                <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2">
                  <input
                    type="checkbox"
                    checked={noBuy}
                    onChange={(event) => setNoBuy(event.target.checked)}
                  />
                  Ignore buys
                </label>
                <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2">
                  <input
                    type="checkbox"
                    checked={noSell}
                    onChange={(event) => setNoSell(event.target.checked)}
                  />
                  Ignore sells
                </label>
                <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2">
                  <input
                    type="checkbox"
                    checked={emitHolds}
                    onChange={(event) => setEmitHolds(event.target.checked)}
                  />
                  Log hold signals
                </label>
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-3 border-t border-border pt-6">
            <Button
              type="button"
              className="px-5 py-2"
              disabled={submitMutation.isPending || terminalCatalogQuery.isLoading}
              onClick={() => submitMutation.mutate()}
            >
              {submitMutation.isPending ? "Starting…" : startLabel}
            </Button>
            {terminalCatalogQuery.isError && (
              <span className="text-sm text-red-400">Could not load strategies.</span>
            )}
          </div>

          {submitMutation.isError && (
            <JobErrorAlert error={submitMutation.error} />
          )}
        </div>
      </Card>
    </div>
  );
}
