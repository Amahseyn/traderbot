/** Mirrors `traderbot/integrations/coinbeacon/paths.py` and `coinbeacon_run` cost model. */

export const TREND_EXCHANGES = [
  "binance",
  "binance-futures",
  "bybit-futures",
  "okx-futures",
  "gateio-futures",
  "htx-futures",
] as const;

export const TREND_SORT_TIMEFRAMES = ["15m", "1h", "4h", "1d", "1w"] as const;

export const DEFAULT_CREDIT_RESERVE = 50;

export function estimateDiscoveryCredits(options: {
  screenerPresetCount: number;
  includeContext: boolean;
  detailTopN: number;
}): number {
  const presets = Math.max(0, options.screenerPresetCount);
  const detail = Math.max(0, options.detailTopN);
  let total = 5 + presets * 5 + detail;
  if (options.includeContext) {
    total += 3;
  }
  return total;
}
