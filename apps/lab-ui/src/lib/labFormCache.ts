import type { PipelineDataSectionState } from "@/components/PipelineDataSection";
import { DEFAULT_PIPELINE_DATA_STATE } from "@/components/PipelineDataSection";

const CUSTOM_RESEARCH_KEY = "traderbot.lab.customResearchDraft";
const LIVE_TRADING_KEY = "traderbot.lab.liveTradingDraft";
const DRAFT_VERSION = 1;

export type StrategyPickMode = "all" | "one" | "subset";

export type CustomResearchDraft = {
  version: typeof DRAFT_VERSION;
  dataState: PipelineDataSectionState;
  compareStrategies: boolean;
  maxStrategies: string;
  strategyPickMode: StrategyPickMode;
  singleStrategyId: string;
  enabledStrategyIds: string[];
  cash: string;
  feePct: string;
  execution: string;
  vectorbt: boolean;
  visualize: boolean;
  limitRunWindow: boolean;
  runStartLocal: string;
  runEndLocal: string;
  useOptimizedStrategyParams: boolean;
  optimizeBeforeCompare: boolean;
  optimizeSelectionMode: "validation" | "in_sample";
  optimizeHoldoutBars: string;
  strategyManualParams: Record<string, unknown>;
};

export type LiveTradingDraft = {
  version: typeof DRAFT_VERSION;
  executionMode: "once" | "continuous";
  multiRun: boolean;
  batchMarkets: Array<{ symbol: string; src: string; dst: string; label: string }>;
  horizons: string[];
  liveExchange: "hyperliquid" | "nobitex";
  orderMode: "paper" | "live";
  strategyId: string;
  multiStrategy: boolean;
  batchStrategyIds: string[];
  marketSymbol: string | null;
  src: string;
  dst: string;
  noBuy: boolean;
  noSell: boolean;
  emitHolds: boolean;
  showAdvanced: boolean;
  continuousLimit: "until_stopped" | "max_cycles";
  maxSteps: string;
  useOptimized: boolean;
  applySweepWinner: boolean;
  optimizeBeforeRun: boolean;
  strategyParams: Record<string, unknown>;
  paperInitialCash: string;
  liveQuoteBudget: string;
  useLiveQuoteBudget: boolean;
};

function readJson<T>(key: string, parse: (raw: unknown) => T | null): T | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      return null;
    }
    return parse(JSON.parse(raw));
  } catch {
    return null;
  }
}

function writeJson(key: string, value: unknown): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // quota or private mode — ignore
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function loadCustomResearchDraft(): CustomResearchDraft | null {
  return readJson(CUSTOM_RESEARCH_KEY, (raw) => {
    if (!isRecord(raw) || raw.version !== DRAFT_VERSION) {
      return null;
    }
    const dataState = isRecord(raw.dataState)
      ? { ...DEFAULT_PIPELINE_DATA_STATE, ...raw.dataState }
      : DEFAULT_PIPELINE_DATA_STATE;
    const strategyPickMode =
      raw.strategyPickMode === "all" || raw.strategyPickMode === "one" || raw.strategyPickMode === "subset"
        ? raw.strategyPickMode
        : "all";
    const enabledStrategyIds = Array.isArray(raw.enabledStrategyIds)
      ? raw.enabledStrategyIds.filter((id): id is string => typeof id === "string")
      : [];
    return {
      version: DRAFT_VERSION,
      dataState: dataState as PipelineDataSectionState,
      compareStrategies: raw.compareStrategies !== false,
      maxStrategies: typeof raw.maxStrategies === "string" ? raw.maxStrategies : "",
      strategyPickMode,
      singleStrategyId: typeof raw.singleStrategyId === "string" ? raw.singleStrategyId : "",
      enabledStrategyIds,
      cash: typeof raw.cash === "string" ? raw.cash : "10000",
      feePct: typeof raw.feePct === "string" ? raw.feePct : "0.045",
      execution: typeof raw.execution === "string" ? raw.execution : "next_open",
      vectorbt: raw.vectorbt !== false,
      visualize: raw.visualize !== false,
      limitRunWindow: Boolean(raw.limitRunWindow),
      runStartLocal: typeof raw.runStartLocal === "string" ? raw.runStartLocal : "",
      runEndLocal: typeof raw.runEndLocal === "string" ? raw.runEndLocal : "",
      useOptimizedStrategyParams: raw.useOptimizedStrategyParams !== false,
      optimizeBeforeCompare: Boolean(raw.optimizeBeforeCompare),
      optimizeSelectionMode:
        raw.optimizeSelectionMode === "in_sample" ? "in_sample" : "validation",
      optimizeHoldoutBars: typeof raw.optimizeHoldoutBars === "string" ? raw.optimizeHoldoutBars : "",
      strategyManualParams: isRecord(raw.strategyManualParams) ? raw.strategyManualParams : {},
    };
  });
}

export function saveCustomResearchDraft(draft: CustomResearchDraft): void {
  writeJson(CUSTOM_RESEARCH_KEY, { ...draft, version: DRAFT_VERSION });
}

export function loadLiveTradingDraft(): LiveTradingDraft | null {
  return readJson(LIVE_TRADING_KEY, (raw) => {
    if (!isRecord(raw) || raw.version !== DRAFT_VERSION) {
      return null;
    }
    const batchMarkets = Array.isArray(raw.batchMarkets)
      ? raw.batchMarkets.filter(
          (row): row is LiveTradingDraft["batchMarkets"][number] =>
            isRecord(row) &&
            typeof row.symbol === "string" &&
            typeof row.src === "string" &&
            typeof row.dst === "string" &&
            typeof row.label === "string",
        )
      : [];
    const horizons = Array.isArray(raw.horizons)
      ? raw.horizons.filter((h): h is string => typeof h === "string")
      : ["60"];
    const batchStrategyIds = Array.isArray(raw.batchStrategyIds)
      ? raw.batchStrategyIds.filter((id): id is string => typeof id === "string")
      : ["sma_cross"];
    return {
      version: DRAFT_VERSION,
      executionMode: raw.executionMode === "continuous" ? "continuous" : "once",
      multiRun: Boolean(raw.multiRun),
      batchMarkets,
      horizons: horizons.length > 0 ? horizons : ["60"],
      liveExchange: raw.liveExchange === "nobitex" ? "nobitex" : "hyperliquid",
      orderMode: raw.orderMode === "live" ? "live" : "paper",
      strategyId: typeof raw.strategyId === "string" ? raw.strategyId : "sma_cross",
      multiStrategy: Boolean(raw.multiStrategy),
      batchStrategyIds,
      marketSymbol: typeof raw.marketSymbol === "string" ? raw.marketSymbol : null,
      src: typeof raw.src === "string" ? raw.src : "btc",
      dst: typeof raw.dst === "string" ? raw.dst : "usdt",
      noBuy: Boolean(raw.noBuy),
      noSell: Boolean(raw.noSell),
      emitHolds: Boolean(raw.emitHolds),
      showAdvanced: Boolean(raw.showAdvanced),
      continuousLimit: raw.continuousLimit === "max_cycles" ? "max_cycles" : "until_stopped",
      maxSteps: typeof raw.maxSteps === "string" ? raw.maxSteps : "24",
      useOptimized: Boolean(raw.useOptimized),
      applySweepWinner: Boolean(raw.applySweepWinner),
      optimizeBeforeRun: Boolean(raw.optimizeBeforeRun),
      strategyParams: isRecord(raw.strategyParams) ? raw.strategyParams : {},
      paperInitialCash: typeof raw.paperInitialCash === "string" ? raw.paperInitialCash : "1000",
      liveQuoteBudget: typeof raw.liveQuoteBudget === "string" ? raw.liveQuoteBudget : "",
      useLiveQuoteBudget: Boolean(raw.useLiveQuoteBudget),
    };
  });
}

export function saveLiveTradingDraft(draft: LiveTradingDraft): void {
  writeJson(LIVE_TRADING_KEY, { ...draft, version: DRAFT_VERSION });
}

export function clearCustomResearchDraft(): void {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(CUSTOM_RESEARCH_KEY);
  }
}

export function clearLiveTradingDraft(): void {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(LIVE_TRADING_KEY);
  }
}
