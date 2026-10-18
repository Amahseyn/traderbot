import type { LiveStrategyRankRow } from "@/lib/api";
import type { StrategyLike } from "@/lib/strategySelection";

const MODEL_STRATEGY_IDS = new Set(["online_logistic", "ensemble", "finrl_ema_intraday"]);

/** Strategies that use learned signals or meta-combination (shown under “Models”). */
export function isModelDrivenStrategy(strategy: StrategyLike): boolean {
  const style = (strategy.style ?? "").trim().toLowerCase();
  if (style === "ml" || style === "meta") {
    return true;
  }
  const id = strategy.id.trim().toLowerCase();
  if (MODEL_STRATEGY_IDS.has(id)) {
    return true;
  }
  return id.startsWith("finrl_");
}

export function formatStrategyPerformanceLabel(name: string, rank?: LiveStrategyRankRow): string {
  if (!rank || rank.return_pct == null || !Number.isFinite(rank.return_pct)) {
    return name;
  }
  const sign = rank.return_pct >= 0 ? "+" : "";
  const trades =
    rank.trade_count != null && Number.isFinite(rank.trade_count)
      ? ` · ${rank.trade_count} trades`
      : "";
  const rankLabel = rank.rank > 0 ? `#${rank.rank} ` : "";
  return `${rankLabel}${name} (${sign}${rank.return_pct.toFixed(2)}% preview${trades})`;
}

export type StrategyReturnPair = {
  avg_return: number | null;
  best_return: number | null;
};

function finiteReturn(value: number | null | undefined): number | null {
  if (value == null || !Number.isFinite(value)) {
    return null;
  }
  return value;
}

/** Catalog row has at least one completed Custom research backtest with a return. */
export function isCompleteCatalogStats(runs: number, avgReturn: number | null, bestReturn: number | null): boolean {
  if (runs <= 0) {
    return false;
  }
  return finiteReturn(avgReturn) != null || finiteReturn(bestReturn) != null;
}

/** Live preview row finished a default-param backtest on recent closed bars. */
export function isCompleteLivePreview(previewReturn: number | null): boolean {
  return finiteReturn(previewReturn) != null;
}

/** Sort key: higher avg first, then higher best (max) return — matches catalog SQL ordering. */
export function compareByAvgThenBestReturn(left: StrategyReturnPair, right: StrategyReturnPair): number {
  const leftAvg = finiteReturn(left.avg_return) ?? -Infinity;
  const rightAvg = finiteReturn(right.avg_return) ?? -Infinity;
  if (rightAvg !== leftAvg) {
    return rightAvg - leftAvg;
  }
  const leftBest = finiteReturn(left.best_return) ?? -Infinity;
  const rightBest = finiteReturn(right.best_return) ?? -Infinity;
  if (rightBest !== leftBest) {
    return rightBest - leftBest;
  }
  return 0;
}

/** Best catalog match requires both avg and max (best) return from completed runs. */
export function pickBestMatchByAvgAndMax<T extends StrategyReturnPair & { id: string }>(
  rows: readonly T[],
): T | null {
  const eligible = rows.filter((row) => {
    return (
      finiteReturn(row.avg_return) != null &&
      finiteReturn(row.best_return) != null
    );
  });
  if (eligible.length === 0) {
    return null;
  }
  return [...eligible].sort((left, right) => compareByAvgThenBestReturn(left, right))[0] ?? null;
}

export function compareByPreviewReturn(
  leftPreview: number | null,
  rightPreview: number | null,
): number {
  const left = finiteReturn(leftPreview) ?? -Infinity;
  const right = finiteReturn(rightPreview) ?? -Infinity;
  return right - left;
}
