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

export type PerformanceRow = {
  id: string;
  name: string;
  summary?: string;
  style: string;
  catalogRuns: number;
  catalogBest: number | null;
  catalogAvg: number | null;
  catalogWinRate: number | null;
  previewReturn: number | null;
  previewDrawdown: number | null;
  previewTrades: number | null;
  previewWinRate: number | null;
  sweepReturn: number | null;
  sweepHoldout: number | null;
  rank: number | null;
};

export type StrategyFilters = {
  query?: string;
  style?: string;
  outcome?: string; // "" | "all" | "profitable" | "high_return" | "loss"
  winRate?: string; // "" | "all" | "high" (>=60) | "positive" (>=50) | "low" (<50)
  activity?: string; // "" | "all" | "complete_only" | "with_runs"
};

export type StrategySortKey =
  | "catalog_avg_desc"
  | "catalog_avg_asc"
  | "catalog_best_desc"
  | "catalog_win_rate_desc"
  | "catalog_runs_desc"
  | "preview_return_desc"
  | "preview_win_rate_desc"
  | "preview_dd_asc"
  | "win_rate_desc"
  | "name_asc";

export function filterPerformanceRows(
  rows: PerformanceRow[],
  filters: StrategyFilters,
): PerformanceRow[] {
  const query = filters.query?.trim().toLowerCase();
  const style = filters.style?.trim().toLowerCase();
  const outcome = filters.outcome?.trim().toLowerCase();
  const winRate = filters.winRate?.trim().toLowerCase();
  const activity = filters.activity?.trim().toLowerCase();

  return rows.filter((row) => {
    if (query) {
      const matchName = row.name.toLowerCase().includes(query);
      const matchId = row.id.toLowerCase().includes(query);
      const matchStyle = row.style.toLowerCase().includes(query);
      const matchSummary = (row.summary ?? "").toLowerCase().includes(query);
      if (!matchName && !matchId && !matchStyle && !matchSummary) {
        return false;
      }
    }

    if (style && style !== "all" && style !== "") {
      if (row.style.toLowerCase() !== style) {
        return false;
      }
    }

    if (activity === "complete_only") {
      const isComplete =
        isCompleteCatalogStats(row.catalogRuns, row.catalogAvg, row.catalogBest) ||
        isCompleteLivePreview(row.previewReturn);
      if (!isComplete) return false;
    } else if (activity === "with_runs") {
      if (row.catalogRuns <= 0) return false;
    }

    if (outcome && outcome !== "all" && outcome !== "") {
      const bestRet = Math.max(row.catalogAvg ?? -Infinity, row.previewReturn ?? -Infinity);
      if (bestRet === -Infinity) return false;
      if (outcome === "profitable" && bestRet <= 0) return false;
      if (outcome === "high_return" && bestRet < 5.0) return false;
      if (outcome === "loss" && bestRet >= 0) return false;
      if (outcome === "positive_catalog" && (row.catalogAvg == null || row.catalogAvg <= 0)) return false;
      if (outcome === "positive_preview" && (row.previewReturn == null || row.previewReturn <= 0)) return false;
    }

    if (winRate && winRate !== "all" && winRate !== "") {
      const rate = row.catalogWinRate ?? row.previewWinRate;
      if (rate == null) return false;
      if (winRate === "high" && rate < 60) return false;
      else if (winRate === "positive" && rate < 50) return false;
      else if (winRate === "low" && rate >= 50) return false;
      else if (!Number.isNaN(Number(winRate))) {
        if (rate < Number(winRate)) return false;
      }
    }

    return true;
  });
}

export function sortPerformanceRows(
  rows: PerformanceRow[],
  sortBy: StrategySortKey = "catalog_avg_desc",
): PerformanceRow[] {
  return [...rows].sort((left, right) => {
    switch (sortBy) {
      case "catalog_avg_desc":
        return compareByAvgThenBestReturn(
          { avg_return: left.catalogAvg, best_return: left.catalogBest },
          { avg_return: right.catalogAvg, best_return: right.catalogBest },
        );
      case "catalog_avg_asc": {
        const lAvg = finiteReturn(left.catalogAvg);
        const rAvg = finiteReturn(right.catalogAvg);
        if (lAvg == null && rAvg != null) return 1;
        if (lAvg != null && rAvg == null) return -1;
        if (lAvg != null && rAvg != null && lAvg !== rAvg) return lAvg - rAvg;
        const lBest = finiteReturn(left.catalogBest);
        const rBest = finiteReturn(right.catalogBest);
        if (lBest == null && rBest != null) return 1;
        if (lBest != null && rBest == null) return -1;
        if (lBest != null && rBest != null && lBest !== rBest) return lBest - rBest;
        return 0;
      }
      case "catalog_best_desc": {
        const l = finiteReturn(left.catalogBest) ?? -Infinity;
        const r = finiteReturn(right.catalogBest) ?? -Infinity;
        return r !== l ? r - l : (finiteReturn(right.catalogAvg) ?? -Infinity) - (finiteReturn(left.catalogAvg) ?? -Infinity);
      }
      case "catalog_win_rate_desc": {
        const l = finiteReturn(left.catalogWinRate);
        const r = finiteReturn(right.catalogWinRate);
        if (l == null && r != null) return 1;
        if (l != null && r == null) return -1;
        if (l != null && r != null && l !== r) return r - l;
        return (finiteReturn(right.catalogAvg) ?? -Infinity) - (finiteReturn(left.catalogAvg) ?? -Infinity);
      }
      case "win_rate_desc": {
        const l = finiteReturn(left.catalogWinRate ?? left.previewWinRate);
        const r = finiteReturn(right.catalogWinRate ?? right.previewWinRate);
        if (l == null && r != null) return 1;
        if (l != null && r == null) return -1;
        if (l != null && r != null && l !== r) return r - l;
        return (finiteReturn(right.catalogAvg ?? right.previewReturn) ?? -Infinity) - (finiteReturn(left.catalogAvg ?? left.previewReturn) ?? -Infinity);
      }
      case "catalog_runs_desc": {
        const delta = right.catalogRuns - left.catalogRuns;
        return delta !== 0 ? delta : (finiteReturn(right.catalogAvg) ?? -Infinity) - (finiteReturn(left.catalogAvg) ?? -Infinity);
      }
      case "preview_return_desc":
        return compareByPreviewReturn(left.previewReturn, right.previewReturn);
      case "preview_win_rate_desc": {
        const l = finiteReturn(left.previewWinRate) ?? -Infinity;
        const r = finiteReturn(right.previewWinRate) ?? -Infinity;
        return r - l;
      }
      case "preview_dd_asc": {
        const l = finiteReturn(left.previewDrawdown) ?? Infinity;
        const r = finiteReturn(right.previewDrawdown) ?? Infinity;
        return l - r;
      }
      case "name_asc":
        return left.name.localeCompare(right.name);
      default:
        return 0;
    }
  });
}

export function compareByPreviewReturn(
  leftPreview: number | null,
  rightPreview: number | null,
): number {
  const left = finiteReturn(leftPreview) ?? -Infinity;
  const right = finiteReturn(rightPreview) ?? -Infinity;
  return right - left;
}
