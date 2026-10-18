import { minutesFromResolution } from "@/lib/format";

export const MAX_LIVE_BATCH_COMBOS = 16;

export type LiveBatchMarket = {
  src: string;
  dst: string;
  symbol: string;
};

export type LiveMarketCombo = LiveBatchMarket & {
  interval: string;
};

export type LiveRunCombo = LiveMarketCombo & {
  strategyId: string;
};

export const DEFAULT_LIVE_HORIZON = "60";

/** User-selected horizons; falls back to 1h when nothing is checked. */
export function resolvedHorizonsForLiveRun(horizons: string[]): string[] {
  const ordered: string[] = [];
  const seen = new Set<string>();
  for (const raw of horizons) {
    const key = raw.trim();
    if (!key || seen.has(key)) {
      continue;
    }
    seen.add(key);
    ordered.push(key);
  }
  return ordered.length > 0 ? ordered : [DEFAULT_LIVE_HORIZON];
}

export function marketCombosForLiveRun(options: {
  multiRun: boolean;
  src: string;
  dst: string;
  marketSymbol: string | null;
  batchMarkets: LiveBatchMarket[];
  horizons: string[];
}): LiveMarketCombo[] {
  const { multiRun, src, dst, marketSymbol, batchMarkets, horizons } = options;
  const intervals = resolvedHorizonsForLiveRun(horizons);
  if (!multiRun) {
    const base = {
      src: src.trim().toLowerCase(),
      dst: dst.trim().toLowerCase(),
      symbol: marketSymbol ?? "",
    };
    return intervals.map((resolution) => ({
      ...base,
      interval: resolution,
    }));
  }
  const combos: LiveMarketCombo[] = [];
  for (const market of batchMarkets) {
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
}

export function strategyIdsForLiveRun(options: {
  multiStrategy: boolean;
  strategyId: string;
  batchStrategyIds: string[];
}): string[] {
  const { multiStrategy, strategyId, batchStrategyIds } = options;
  if (!multiStrategy) {
    return [strategyId];
  }
  const ordered: string[] = [];
  const seen = new Set<string>();
  for (const raw of batchStrategyIds) {
    const key = raw.trim();
    if (!key || seen.has(key)) {
      continue;
    }
    seen.add(key);
    ordered.push(key);
  }
  return ordered;
}

export function buildLiveRunCombos(options: {
  multiRun: boolean;
  src: string;
  dst: string;
  marketSymbol: string | null;
  batchMarkets: LiveBatchMarket[];
  horizons: string[];
  multiStrategy: boolean;
  strategyId: string;
  batchStrategyIds: string[];
}): LiveRunCombo[] {
  const markets = marketCombosForLiveRun(options);
  const strategies = strategyIdsForLiveRun({
    multiStrategy: options.multiStrategy,
    strategyId: options.strategyId,
    batchStrategyIds: options.batchStrategyIds,
  });
  const combos: LiveRunCombo[] = [];
  for (const market of markets) {
    for (const strategyId of strategies) {
      combos.push({ ...market, strategyId });
    }
  }
  return combos;
}

/** Poll interval aligned to a job's candle size (min 5s). */
export function pollSecondsForResolution(resolution: string): number {
  const minutes = minutesFromResolution(resolution);
  const seconds = minutes != null ? Math.max(15, minutes * 60) : 60;
  return Math.max(5, seconds);
}

export function comboUniqueKey(combo: LiveRunCombo): string {
  return `${combo.symbol}|${combo.interval}|${combo.strategyId}`;
}

export function assertUniqueLiveRunCombos(combos: LiveRunCombo[]): void {
  const keys = combos.map(comboUniqueKey);
  if (new Set(keys).size !== keys.length) {
    throw new Error("duplicate live run combo");
  }
}
