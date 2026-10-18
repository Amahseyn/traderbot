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
import { api, formatApiError, type LiveStrategyRankRow, type MarketSpec } from "@/lib/api";
import { formatStrategyPerformanceLabel } from "@/lib/strategyPerformance";
import { formatDurationMinutes, formatResolutionLabel, minutesFromResolution } from "@/lib/format";
import {
  buildLiveRunCombos,
  DEFAULT_LIVE_HORIZON,
  MAX_LIVE_BATCH_COMBOS,
  pollSecondsForResolution,
  resolvedHorizonsForLiveRun,
} from "@/lib/liveRunCombos";
import { loadLiveTradingDraft, saveLiveTradingDraft } from "@/lib/labFormCache";
import { EmptyState, ErrorState, Skeleton, TableSkeleton } from "@/components/ui/States";

type ExecutionMode = "once" | "continuous";
type OrderMode = "paper" | "live";
type LiveExchange = "hyperliquid" | "nobitex";
type ContinuousLimit = "until_stopped" | "max_cycles";

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
  exchange: LiveExchange;
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
  const [horizons, setHorizons] = useState<string[]>([DEFAULT_LIVE_HORIZON]);
  const [liveExchange, setLiveExchange] = useState<LiveExchange>("hyperliquid");
  const [orderMode, setOrderMode] = useState<OrderMode>("paper");
  const [strategyId, setStrategyId] = useState("sma_cross");
  const [multiStrategy, setMultiStrategy] = useState(false);
  const [batchStrategyIds, setBatchStrategyIds] = useState<string[]>(["sma_cross"]);
  const [marketSymbol, setMarketSymbol] = useState<string | null>("BTCUSDT");
  const [src, setSrc] = useState("btc");
  const [dst, setDst] = useState("usdt");
  const [noBuy, setNoBuy] = useState(false);
  const [noSell, setNoSell] = useState(false);
  const [emitHolds, setEmitHolds] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [continuousLimit, setContinuousLimit] = useState<ContinuousLimit>("until_stopped");
  const [maxSteps, setMaxSteps] = useState("24");
  const [useOptimized, setUseOptimized] = useState(false);
  const [applySweepWinner, setApplySweepWinner] = useState(false);
  const [optimizeBeforeRun, setOptimizeBeforeRun] = useState(false);
  const [strategyParams, setStrategyParams] = useState<Record<string, unknown>>({});
  const [paperInitialCash, setPaperInitialCash] = useState(() => defaultPaperCash("usdt"));
  const [liveQuoteBudget, setLiveQuoteBudget] = useState("");
  const [useLiveQuoteBudget, setUseLiveQuoteBudget] = useState(false);
  const [formReady, setFormReady] = useState(false);
  const [draftRestored, setDraftRestored] = useState(false);

  useEffect(() => {
    const draft = loadLiveTradingDraft();
    if (draft) {
      setExecutionMode(draft.executionMode);
      setMultiRun(draft.multiRun);
      setBatchMarkets(draft.batchMarkets);
      setHorizons(draft.horizons);
      setLiveExchange(draft.liveExchange);
      setOrderMode(draft.orderMode);
      setStrategyId(draft.strategyId);
      setMultiStrategy(draft.multiStrategy);
      setBatchStrategyIds(draft.batchStrategyIds);
      setMarketSymbol(draft.marketSymbol);
      setSrc(draft.src);
      setDst(draft.dst);
      setNoBuy(draft.noBuy);
      setNoSell(draft.noSell);
      setEmitHolds(draft.emitHolds);
      setShowAdvanced(draft.showAdvanced);
      setContinuousLimit(draft.continuousLimit);
      setMaxSteps(draft.maxSteps);
      setUseOptimized(draft.useOptimized);
      setApplySweepWinner(draft.applySweepWinner);
      setOptimizeBeforeRun(draft.optimizeBeforeRun);
      setStrategyParams(draft.strategyParams);
      setPaperInitialCash(draft.paperInitialCash);
      setLiveQuoteBudget(draft.liveQuoteBudget);
      setUseLiveQuoteBudget(draft.useLiveQuoteBudget);
      setDraftRestored(true);
    }
    setFormReady(true);
  }, []);

  useEffect(() => {
    if (!formReady) {
      return;
    }
    const handle = window.setTimeout(() => {
      saveLiveTradingDraft({
        version: 1,
        executionMode,
        multiRun,
        batchMarkets,
        horizons,
        liveExchange,
        orderMode,
        strategyId,
        multiStrategy,
        batchStrategyIds,
        marketSymbol,
        src,
        dst,
        noBuy,
        noSell,
        emitHolds,
        showAdvanced,
        continuousLimit,
        maxSteps,
        useOptimized,
        applySweepWinner,
        optimizeBeforeRun,
        strategyParams,
        paperInitialCash,
        liveQuoteBudget,
        useLiveQuoteBudget,
      });
    }, 400);
    return () => window.clearTimeout(handle);
  }, [
    formReady,
    executionMode,
    multiRun,
    batchMarkets,
    horizons,
    liveExchange,
    orderMode,
    strategyId,
    multiStrategy,
    batchStrategyIds,
    marketSymbol,
    src,
    dst,
    noBuy,
    noSell,
    emitHolds,
    showAdvanced,
    continuousLimit,
    maxSteps,
    useOptimized,
    applySweepWinner,
    optimizeBeforeRun,
    strategyParams,
    paperInitialCash,
    liveQuoteBudget,
    useLiveQuoteBudget,
  ]);

  const terminalCatalogQuery = useQuery({
    queryKey: ["catalog-terminal"],
    queryFn: () => api.catalogTerminal(true),
  });
  const authQuery = useQuery({ queryKey: ["auth-status"], queryFn: api.authStatus });

  const strategies = terminalCatalogQuery.data?.strategies ?? [];
  const resolutions =
    liveExchange === "hyperliquid"
      ? (terminalCatalogQuery.data?.hyperliquid_resolutions ??
        terminalCatalogQuery.data?.udf_resolutions ??
        ["1", "60", "240", "D"])
      : (terminalCatalogQuery.data?.udf_resolutions ?? ["60", "240", "D"]);

  const activeHorizons = useMemo(() => resolvedHorizonsForLiveRun(horizons), [horizons]);
  const primaryHorizon = activeHorizons[0] ?? DEFAULT_LIVE_HORIZON;
  const previewCash = useMemo(() => {
    const cash = Number(paperInitialCash);
    return Number.isFinite(cash) && cash > 0 ? cash : undefined;
  }, [paperInitialCash]);
  const strategyRanksQuery = useQuery({
    queryKey: ["live-strategy-ranks", liveExchange, src, dst, primaryHorizon, previewCash],
    queryFn: () =>
      api.liveStrategyRanks({
        exchange: liveExchange,
        src,
        dst,
        resolution: primaryHorizon,
        initialCash: previewCash,
      }),
    enabled: Boolean(src && dst),
    staleTime: 120_000,
    retry: 1,
    retryDelay: 2000,
  });
  const strategyRankById = useMemo(() => {
    const map = new Map<string, LiveStrategyRankRow>();
    for (const row of strategyRanksQuery.data?.ranked ?? []) {
      map.set(row.strategy_id, row);
    }
    return map;
  }, [strategyRanksQuery.data]);
  const sortedStrategies = useMemo(() => {
    return [...strategies].sort((left, right) => {
      const leftRank = strategyRankById.get(left.id);
      const rightRank = strategyRankById.get(right.id);
      const leftReturn = leftRank?.return_pct;
      const rightReturn = rightRank?.return_pct;
      if (leftReturn == null && rightReturn == null) {
        return left.id.localeCompare(right.id);
      }
      if (leftReturn == null) {
        return 1;
      }
      if (rightReturn == null) {
        return -1;
      }
      return rightReturn - leftReturn;
    });
  }, [strategies, strategyRankById]);
  const intervalMinutes = minutesFromResolution(primaryHorizon);
  const pollSecondsByHorizon = useMemo(
    () =>
      activeHorizons.map((horizon) => ({
        horizon,
        label: formatResolutionLabel(horizon),
        seconds: pollSecondsForResolution(horizon),
      })),
    [activeHorizons],
  );

  useEffect(() => {
    if (strategies.length === 0) {
      return;
    }
    if (!strategies.some((row) => row.id === strategyId)) {
      setStrategyId(strategies[0].id);
    }
  }, [strategies, strategyId]);

  function selectMarket(market: MarketSpec) {
    setMarketSymbol(market.symbol);
    setSrc(market.src);
    setDst(market.dst);
    setPaperInitialCash(defaultPaperCash(market.dst));
    if (useLiveQuoteBudget) {
      setLiveQuoteBudget(defaultPaperCash(market.dst));
    }
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

  function toggleHorizon(resolution: string) {
    setHorizons((rows) =>
      rows.includes(resolution) ? rows.filter((item) => item !== resolution) : [...rows, resolution],
    );
  }

  function toggleBatchStrategy(id: string) {
    setBatchStrategyIds((rows) =>
      rows.includes(id) ? rows.filter((item) => item !== id) : [...rows, id],
    );
  }

  const liveRunCombos = useMemo(
    () =>
      buildLiveRunCombos({
        multiRun,
        src,
        dst,
        marketSymbol,
        batchMarkets,
        horizons,
        multiStrategy,
        strategyId,
        batchStrategyIds,
      }),
    [
      multiRun,
      batchMarkets,
      horizons,
      marketSymbol,
      src,
      dst,
      multiStrategy,
      strategyId,
      batchStrategyIds,
    ],
  );

  useEffect(() => {
    onSessionChange?.({
      src,
      dst,
      interval: primaryHorizon,
      marketSymbol,
      exchange: liveExchange,
    });
  }, [src, dst, primaryHorizon, marketSymbol, liveExchange, onSessionChange]);

  const liveOrders = orderMode === "live";

  const baseJobBody = useMemo(() => {
    const body: Record<string, unknown> = {
      src: src.trim().toLowerCase(),
      dst: dst.trim().toLowerCase(),
      interval: primaryHorizon,
      market_symbol: marketSymbol,
      live: liveOrders,
      no_buy: noBuy,
      no_sell: noSell,
      emit_holds: emitHolds,
      use_optimized_defaults: useOptimized || optimizeBeforeRun,
      apply_sweep_winner: applySweepWinner || optimizeBeforeRun,
      optimize_before_run: optimizeBeforeRun && !liveOrders,
      optimize_max_bars: 100,
      optimize_holdout_bars: 20,
      exchange: liveExchange,
    };
    if (!liveOrders) {
      const cash = Number(paperInitialCash);
      if (Number.isFinite(cash) && cash > 0) {
        body.paper_initial_cash = cash;
      }
    } else if (useLiveQuoteBudget) {
      const budget = Number(liveQuoteBudget);
      if (Number.isFinite(budget) && budget > 0) {
        body.live_quote_budget = budget;
      }
    }
    if (!multiStrategy && !useOptimized && !optimizeBeforeRun) {
      Object.assign(body, strategyParams);
    }
    if (executionMode === "continuous") {
      if (continuousLimit === "until_stopped") {
        body.until_stopped = true;
      } else {
        body.max_steps = Number(maxSteps);
      }
    }
    return body;
  }, [
    multiStrategy,
    marketSymbol,
    src,
    dst,
    primaryHorizon,
    liveOrders,
    paperInitialCash,
    useLiveQuoteBudget,
    liveQuoteBudget,
    noBuy,
    noSell,
    emitHolds,
    useOptimized,
    applySweepWinner,
    optimizeBeforeRun,
    liveExchange,
    strategyParams,
    executionMode,
    continuousLimit,
    maxSteps,
  ]);

  const submitMutation = useMutation({
    mutationFn: async () => {
      if (liveOrders && liveExchange === "nobitex" && !authQuery.data?.api_keys_configured) {
        throw new Error("Configure Nobitex API keys in Settings before live orders.");
      }
      if (liveOrders && liveExchange === "hyperliquid" && !authQuery.data?.hyperliquid_wallet_configured) {
        throw new Error("Configure Hyperliquid wallet in Settings before live orders.");
      }
      if (
        liveOrders &&
        liveExchange === "hyperliquid" &&
        !authQuery.data?.hyperliquid_trading_configured
      ) {
        throw new Error("Add Hyperliquid private key in Settings to place live perp orders.");
      }
      if (executionMode === "continuous" && continuousLimit === "max_cycles") {
        const steps = Number(maxSteps);
        if (!Number.isFinite(steps) || steps < 1) {
          throw new Error("Enter at least one cycle.");
        }
      }
      if (multiStrategy && batchStrategyIds.length === 0) {
        throw new Error("Select at least one strategy in the batch list.");
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
          `Too many combinations (${liveRunCombos.length}). Limit is ${MAX_LIVE_BATCH_COMBOS} (markets × horizons × strategies).`,
        );
      }
      const jobType = executionMode === "once" ? "terminal-once" : "terminal-live";
      const started: Array<{ id: string; status: string }> = [];
      for (const combo of liveRunCombos) {
        const body = {
          ...baseJobBody,
          strategy: combo.strategyId,
          src: combo.src,
          dst: combo.dst,
          interval: combo.interval,
          market_symbol: combo.symbol,
          ...(executionMode === "continuous"
            ? { poll_sec: pollSecondsForResolution(combo.interval) }
            : {}),
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

  const hyperliquidReady = authQuery.data?.hyperliquid_wallet_configured === true;
  const nobitexKeysReady = authQuery.data?.api_keys_configured === true;
  const liveCredentialsReady =
    liveExchange === "hyperliquid" ? hyperliquidReady : nobitexKeysReady;
  const pairLabel = `${src.toUpperCase()}/${dst.toUpperCase()}`;

  const comboCount = liveRunCombos.length;
  const optimizeComboLabels = useMemo(() => {
    if (!optimizeBeforeRun || liveRunCombos.length === 0) {
      return [];
    }
    return liveRunCombos.map((combo) => {
      const pair =
        combo.symbol.trim() ||
        `${combo.src.toUpperCase()}/${combo.dst.toUpperCase()}`;
      return `${pair} · ${formatResolutionLabel(combo.interval)} · ${combo.strategyId}`;
    });
  }, [optimizeBeforeRun, liveRunCombos]);
  const startLabel =
    comboCount > 1
      ? executionMode === "once"
        ? `Run ${comboCount} single checks${optimizeBeforeRun ? " (tune first)" : ""}`
        : continuousLimit === "until_stopped"
          ? `Start ${comboCount} sessions${optimizeBeforeRun ? " (tune first)" : ""}`
          : `Start ${comboCount} polling jobs${optimizeBeforeRun ? " (tune first)" : ""}`
      : executionMode === "once"
        ? optimizeBeforeRun
          ? "Run single check (tune first)"
          : "Run single check"
        : continuousLimit === "until_stopped"
          ? optimizeBeforeRun
            ? "Start session (tune first)"
            : "Start continuous session"
          : optimizeBeforeRun
            ? "Start polling job (tune first)"
            : "Start polling job";

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.65fr)]">
      <div className="space-y-4">
        {draftRestored && (
          <p className="text-xs text-muted">
            Restored your last live session settings from this browser. Changes save automatically.
          </p>
        )}
        <Card
          title="How it works"
          description="Strategies read the latest closed candle from your chosen exchange (Hyperliquid by default)."
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
              <span className="text-muted">Hyperliquid wallet</span>
              <span className={hyperliquidReady ? "text-emerald-300" : "text-amber-200"}>
                {hyperliquidReady ? "Ready" : "Not set"}
              </span>
            </li>
            <li className="flex items-center justify-between gap-2">
              <span className="text-muted">Nobitex API keys</span>
              <span className={nobitexKeysReady ? "text-emerald-300" : "text-amber-200"}>
                {nobitexKeysReady ? "Ready" : "Not set"}
              </span>
            </li>
            <li className="text-xs text-muted">
              Paper mode works without credentials. Live Hyperliquid needs wallet + private key; Nobitex
              needs API keys — configure in{" "}
              <Link href="/settings" className="text-accent hover:underline">Settings</Link>.
            </li>
          </ul>
        </Card>
      </div>

      <Card
        title="Configure session"
        description="Pick exchange, market, strategy, and paper vs live execution."
      >
        <div className="space-y-6">
          <div>
            <h3 className="mb-2 text-sm font-medium text-white">Exchange</h3>
            <SegmentedOption
              value={liveExchange}
              onChange={(value) => {
                setLiveExchange(value);
                if (value === "hyperliquid" && dst === "rls") {
                  setDst("usdt");
                  setMarketSymbol("BTCUSDT");
                  setPaperInitialCash(defaultPaperCash("usdt"));
                }
                if (value === "nobitex" && dst === "usdt" && marketSymbol === "BTCUSDT") {
                  setDst("rls");
                  setMarketSymbol("BTCIRT");
                  setPaperInitialCash(defaultPaperCash("rls"));
                }
              }}
              options={[
                {
                  id: "hyperliquid",
                  label: "Hyperliquid",
                  description: "USDC perps — default for live tests.",
                },
                {
                  id: "nobitex",
                  label: "Nobitex",
                  description: "IRT/USDT spot via Nobitex UDF.",
                },
              ]}
            />
          </div>

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
                  label: "Simulated live",
                  description:
                    "Paper wallet: starting cash is also the max the bot may deploy (same as live quote budget).",
                },
                {
                  id: "live",
                  label: "Live",
                  description: "Market orders on Nobitex (full wallet size).",
                },
              ]}
            />
            {orderMode === "live" && (
              <div className="mt-3 space-y-3">
                <p className="rounded-lg border border-red-500/30 bg-red-950/30 px-3 py-2 text-sm text-red-200/90">
                  Live mode places market orders on Nobitex. Start with paper, or enable “Ignore buys”
                  under advanced options while you validate signals.
                </p>
                <label className="flex items-start gap-2 rounded-lg border border-border bg-surface/60 px-3 py-2 text-sm text-slate-200">
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={useLiveQuoteBudget}
                    onChange={(event) => {
                      const checked = event.target.checked;
                      setUseLiveQuoteBudget(checked);
                      if (checked && !liveQuoteBudget.trim()) {
                        setLiveQuoteBudget(defaultPaperCash(dst));
                      }
                    }}
                  />
                  <span>
                    <span className="font-medium text-white">Limit to manual quote balance</span>
                    <span className="mt-1 block text-xs leading-snug text-muted">
                      Cap each buy to this amount (and sell only base bought in this session). Leave
                      off to use your full Nobitex wallet.
                    </span>
                  </span>
                </label>
                {useLiveQuoteBudget && (
                  <Field
                    label="Quote balance to trade"
                    hint={
                      dst === "usdt"
                        ? "USDT available for buys (e.g. 1,000)."
                        : "RLS available for buys (e.g. 10,000,000)."
                    }
                  >
                    <TextInput
                      type="number"
                      min={1}
                      step={1}
                      className="max-w-xs"
                      value={liveQuoteBudget}
                      onChange={(event) => setLiveQuoteBudget(event.target.value)}
                    />
                  </Field>
                )}
              </div>
            )}
            {orderMode === "paper" && (
              <div className="mt-3 space-y-3">
                <Field
                  label="Paper wallet size (also capital cap)"
                  hint={
                    dst === "usdt"
                      ? "USDT for paper trading and optimizer (default 1,000). Buys cannot exceed this total."
                      : "RLS for paper trading and optimizer (default 10,000,000). Buys cannot exceed this total."
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

          <div className="space-y-4 border-t border-border pt-6">
            <div>
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-medium text-white">Strategies</h3>
                <label className="flex cursor-pointer items-center gap-2 text-xs text-slate-300">
                  <input
                    type="checkbox"
                    checked={multiStrategy}
                    onChange={(event) => {
                      const enabled = event.target.checked;
                      setMultiStrategy(enabled);
                      if (enabled) {
                        setBatchStrategyIds((rows) =>
                          rows.length > 0 ? rows : [strategyId],
                        );
                      }
                    }}
                  />
                  Multi strategy — one job per strategy (combine with multi market)
                </label>
              </div>
              {strategyRanksQuery.isSuccess && sortedStrategies.length > 0 && (
                <p className="mb-2 text-xs text-muted">
                  Sorted by preview return on the last {strategyRanksQuery.data?.bars ?? "—"} closed{" "}
                  {formatResolutionLabel(primaryHorizon)} candles (default params). Top:{" "}
                  <span className="text-slate-300">
                    {formatStrategyPerformanceLabel(
                      sortedStrategies[0].name || sortedStrategies[0].id,
                      strategyRankById.get(sortedStrategies[0].id),
                    )}
                  </span>
                </p>
              )}
              {strategyRanksQuery.isError && (
                <p className="mb-2 text-xs text-amber-200/90">
                  Could not rank strategies on live candles ({formatApiError(strategyRanksQuery.error)}).
                  Restart <code className="text-slate-300">./run-lab-api.sh</code> if the endpoint is missing (404).
                  List stays alphabetical until ranks load.
                </p>
              )}
              {multiStrategy ? (
                <div className="max-h-48 space-y-2 overflow-y-auto rounded-xl border border-border bg-surface/50 p-3">
                  {strategies.length === 0 ? (
                    <p className="text-sm text-muted">Loading strategies…</p>
                  ) : strategyRanksQuery.isLoading && sortedStrategies.length === 0 ? (
                    <p className="text-sm text-muted">Loading strategy rankings…</p>
                  ) : (
                    sortedStrategies.map((row) => {
                      const checked = batchStrategyIds.includes(row.id);
                      return (
                        <label
                          key={row.id}
                          className={`flex cursor-pointer items-center gap-2 rounded-lg border px-2.5 py-1.5 text-sm ${
                            checked
                              ? "border-accent/50 bg-accent/10 text-white"
                              : "border-transparent text-slate-300 hover:bg-surface"
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleBatchStrategy(row.id)}
                          />
                          {formatStrategyPerformanceLabel(row.name || row.id, strategyRankById.get(row.id))}
                        </label>
                      );
                    })
                  )}
                  <p className="text-xs text-muted">
                    {batchStrategyIds.length === 0
                      ? "Pick at least one strategy."
                      : `${batchStrategyIds.length} strateg${batchStrategyIds.length === 1 ? "y" : "ies"} in batch.`}
                  </p>
                </div>
              ) : (
                <Field
                  label="Strategy"
                  hint={
                    strategyRanksQuery.isFetching
                      ? "Refreshing preview ranks from exchange candles…"
                      : strategyRanksQuery.isSuccess
                        ? `Best preview on ${strategyRanksQuery.data?.symbol ?? pairLabel} first.`
                        : undefined
                  }
                >
                  <SelectInput
                    value={strategyId}
                    onChange={(event) => setStrategyId(event.target.value)}
                  >
                    {sortedStrategies.map((row) => (
                      <option key={row.id} value={row.id}>
                        {formatStrategyPerformanceLabel(row.name || row.id, strategyRankById.get(row.id))}
                      </option>
                    ))}
                  </SelectInput>
                </Field>
              )}
            </div>

          </div>

          <div>
            <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="text-sm font-medium text-white">Market & horizons</h3>
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
              Multi run — several markets and/or horizons (one job per market × horizon
              {multiStrategy ? " × strategy" : ""})
            </label>
            <MarketSearchPicker
              selectedSymbol={marketSymbol}
              onSelect={selectMarket}
              defaultMarketScope={liveExchange === "hyperliquid" ? "hyperliquid_all" : "nobitex_all"}
              batchMode={multiRun}
              batchSymbols={batchMarkets.map((row) => row.symbol)}
              onToggleBatch={toggleBatchMarket}
              onClearBatch={clearBatchMarkets}
              maxBatchSelect={MAX_LIVE_BATCH_COMBOS}
            />
            <div className="mt-4 space-y-2 rounded-xl border border-border bg-surface/50 p-4">
              <p className="text-xs font-medium text-slate-300">Horizons to test</p>
              <p className="text-xs text-muted">
                Each job uses the candle size for its horizon. Pick one or more — every market you
                select runs at each checked horizon.
              </p>
              <div className="flex flex-wrap gap-2">
                {resolutions.map((resolution) => {
                  const checked = horizons.includes(resolution);
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
                        onChange={() => toggleHorizon(resolution)}
                      />
                      {resolution} — {formatResolutionLabel(resolution)}
                    </label>
                  );
                })}
              </div>
              <p className="text-xs text-muted">
                {horizons.length === 0
                  ? `No horizon checked — jobs default to ${formatResolutionLabel(DEFAULT_LIVE_HORIZON)}.`
                  : `Active: ${activeHorizons.map((h) => formatResolutionLabel(h)).join(", ")}.`}
                {multiRun && batchMarkets.length === 0
                  ? " Select batch markets above."
                  : !multiRun
                    ? ` ${comboCount} job${comboCount === 1 ? "" : "s"} for the selected market.`
                    : ` Ready to start ${comboCount} job${comboCount === 1 ? "" : "s"}.`}
                {comboCount > MAX_LIVE_BATCH_COMBOS &&
                  ` Too many combinations — remove markets, horizons, or strategies (max ${MAX_LIVE_BATCH_COMBOS}).`}
              </p>
            </div>
          </div>

          {executionMode === "continuous" && (
            <div className="space-y-4 rounded-xl border border-border bg-surface/50 p-4">
              <h3 className="text-sm font-medium text-white">Polling schedule</h3>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1 text-sm">
                  <p className="text-slate-200">Wait between checks</p>
                  <p className="text-xs text-muted">
                    Set automatically from each job&apos;s horizon (~one closed bar, minimum 5s).
                  </p>
                  <ul className="mt-2 space-y-1 text-xs text-slate-400">
                    {pollSecondsByHorizon.map((row) => (
                      <li key={row.horizon}>
                        {row.label}:{" "}
                        <span className="font-mono text-slate-300">{row.seconds}s</span>
                      </li>
                    ))}
                  </ul>
                </div>
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
                  Each job waits about one bar for its horizon before the next fetch. Checking faster
                  would only repeat the same closed candle.
                </p>
              )}
            </div>
          )}

          <div className="space-y-2 border-t border-border pt-6">
            <h3 className="text-sm font-medium text-white">Strategy parameters</h3>
            {orderMode === "live" ? (
              <p className="rounded-lg border border-border bg-surface/60 px-3 py-2 text-xs text-muted">
                Live orders cannot run the 100-candle pre-session optimizer (API safety). Use paper with{" "}
                <span className="text-slate-300">Optimize before session</span>, then switch to live with
                stored params, or run a Lab sweep on catalog data.
              </p>
            ) : (
              <div className="space-y-2 rounded-xl border border-border bg-surface/50 p-4">
                <label className="flex items-start gap-2 text-sm text-slate-200">
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={optimizeBeforeRun}
                    onChange={(event) => {
                      const checked = event.target.checked;
                      setOptimizeBeforeRun(checked);
                      if (checked) {
                        setUseOptimized(true);
                        setApplySweepWinner(true);
                      }
                    }}
                  />
                  <span>
                    <span className="font-medium text-white">Optimize before session</span>
                    <span className="mt-1 block text-xs leading-snug text-muted">
                      Each job fetches the last 100 closed candles, runs a small grid with train / validation /
                      test selection (fallback to in-sample holdout when too short), saves the winner per market ×
                      interval × strategy, then starts trading.
                    </span>
                  </span>
                </label>
                {optimizeBeforeRun && comboCount > 0 && (
                  <div className="text-xs text-muted">
                    <p className="font-medium text-slate-300">
                      {comboCount} tune{comboCount === 1 ? "" : "s"} before run
                      {comboCount > 1 ? " (one per job)" : ""}:
                    </p>
                    <ul className="mt-1 max-h-28 list-inside list-disc overflow-y-auto text-slate-400">
                      {optimizeComboLabels.slice(0, 8).map((label) => (
                        <li key={label}>{label}</li>
                      ))}
                      {optimizeComboLabels.length > 8 && (
                        <li>…and {optimizeComboLabels.length - 8} more</li>
                      )}
                    </ul>
                  </div>
                )}
              </div>
            )}
            {multiStrategy ? (
              <p className="text-sm text-muted">
                Multi-strategy batches use per-strategy params from the sweep store, or{" "}
                <span className="text-slate-300">Optimize before session</span> above to tune each
                market × horizon × strategy job. Switch off multi strategy to edit knobs for one strategy.
              </p>
            ) : (
              <OptimizedStrategyParamsBlock
                strategyId={strategyId}
                symbol={marketSymbol}
                resolution={primaryHorizon}
                useOptimized={useOptimized}
                onUseOptimizedChange={setUseOptimized}
                manualValues={strategyParams}
                onManualValuesChange={setStrategyParams}
              />
            )}
            <label className="flex items-center gap-2 text-sm text-slate-200">
              <input
                type="checkbox"
                checked={applySweepWinner}
                disabled={!useOptimized}
                onChange={(event) => setApplySweepWinner(event.target.checked)}
              />
              Apply latest sweep winner (explicit approval; never automatic for live)
            </label>
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
              className="w-full px-5 py-2 sm:w-auto"
              disabled={submitMutation.isPending || terminalCatalogQuery.isLoading}
              onClick={() => submitMutation.mutate()}
            >
              {terminalCatalogQuery.isLoading ? "Loading strategies…" : submitMutation.isPending ? "Starting…" : startLabel}
            </Button>
            {terminalCatalogQuery.isError && (
              <ErrorState
                title="Could not load terminal catalog"
                error={terminalCatalogQuery.error}
                hintAuth={false}
                action={
                  <button
                    type="button"
                    className="text-sm text-accent underline"
                    onClick={() => terminalCatalogQuery.refetch()}
                  >
                    Retry
                  </button>
                }
              />
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
