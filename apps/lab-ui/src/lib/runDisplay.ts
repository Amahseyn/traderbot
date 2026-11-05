import type { EvaluationRun } from "@/lib/api";
import { formatResolutionLabel, parseReturnPct } from "@/lib/format";

export type RunListMetrics = {
  returnPct: number | null;
  winRatePct: number | null;
  trades: number | null;
  finalEquity: number | null;
  totalFees: number | null;
  bars: number | null;
  netPnl: number | null;
};

export function extractWinRatePct(metrics: Record<string, unknown> | undefined): number | null {
  if (!metrics || typeof metrics !== "object") return null;

  const wrDirect = metrics.win_rate_pct;
  if (typeof wrDirect === "number" && Number.isFinite(wrDirect)) {
    return wrDirect;
  }
  if (typeof wrDirect === "string" && wrDirect.trim()) {
    const parsed = Number(wrDirect.replace("%", "").trim());
    if (Number.isFinite(parsed)) return parsed;
  }
  if (typeof metrics.trade_win_rate === "number" && Number.isFinite(metrics.trade_win_rate)) {
    return metrics.trade_win_rate <= 1.0
      ? Math.round(metrics.trade_win_rate * 1000000) / 10000
      : metrics.trade_win_rate;
  }
  if (typeof metrics.win_rate === "number" && Number.isFinite(metrics.win_rate)) {
    return metrics.win_rate <= 1.0
      ? Math.round(metrics.win_rate * 1000000) / 10000
      : metrics.win_rate;
  }
  const vbt = metrics.vectorbt;
  if (vbt && typeof vbt === "object" && typeof (vbt as Record<string, unknown>).win_rate_pct === "number") {
    const vbtPct = (vbt as Record<string, unknown>).win_rate_pct;
    if (typeof vbtPct === "number" && Number.isFinite(vbtPct)) {
      return vbtPct;
    }
  }
  if (typeof metrics.vbt_win_rate_pct === "number" && Number.isFinite(metrics.vbt_win_rate_pct)) {
    return metrics.vbt_win_rate_pct;
  }
  if (Array.isArray(metrics.trade_logs) && metrics.trade_logs.length > 0) {
    const logs = metrics.trade_logs as Array<Record<string, unknown>>;
    const initialCash =
      typeof metrics.initial_cash === "number"
        ? metrics.initial_cash
        : Number((metrics.cash_flow as Record<string, unknown> | undefined)?.initial_cash) || 0;
    let position = 0;
    let equityBefore = initialCash || (Number(logs[0]?.cash_before) || 0);
    let openEquity: number | null = null;
    let trips = 0;
    let wins = 0;
    const EPS = 1e-12;

    for (const fill of logs) {
      const equityAfter = Number(fill.equity_after);
      const positionAfter = Number(fill.position_after) || 0;
      if (openEquity === null && Math.abs(position) <= EPS && Math.abs(positionAfter) > EPS) {
        openEquity = equityBefore;
      }
      if (openEquity !== null && Math.abs(positionAfter) <= EPS && Number.isFinite(equityAfter)) {
        trips++;
        if (equityAfter > openEquity) {
          wins++;
        }
        openEquity = null;
      }
      position = positionAfter;
      if (Number.isFinite(equityAfter)) {
        equityBefore = equityAfter;
      }
    }
    if (trips > 0) {
      return (wins / trips) * 100;
    }
  }
  return null;
}

export function runListMetrics(run: EvaluationRun): RunListMetrics {
  const metrics = run.metrics;
  const cashFlow =
    metrics.cash_flow && typeof metrics.cash_flow === "object"
      ? (metrics.cash_flow as Record<string, unknown>)
      : null;

  const trades =
    typeof metrics.trades === "number"
      ? metrics.trades
      : typeof cashFlow?.trades === "number"
        ? cashFlow.trades
        : null;

  const finalEquity =
    typeof metrics.final_equity === "number"
      ? metrics.final_equity
      : typeof cashFlow?.final_equity === "number"
        ? cashFlow.final_equity
        : null;

  const totalFees =
    typeof metrics.total_fees === "number"
      ? metrics.total_fees
      : typeof cashFlow?.total_fees === "number"
        ? cashFlow.total_fees
        : null;

  const bars =
    typeof metrics.bars === "number"
      ? metrics.bars
      : typeof run.data_context.bars === "number"
        ? run.data_context.bars
        : null;

  const initialCash =
    typeof metrics.initial_cash === "number"
      ? metrics.initial_cash
      : typeof cashFlow?.initial_cash === "number"
        ? cashFlow.initial_cash
        : null;

  const netPnl =
    typeof cashFlow?.net_pnl === "number"
      ? cashFlow.net_pnl
      : finalEquity != null && initialCash != null
        ? finalEquity - initialCash
        : null;

  return {
    returnPct: parseReturnPct(metrics),
    winRatePct: extractWinRatePct(metrics),
    trades,
    finalEquity,
    totalFees,
    bars,
    netPnl,
  };
}

export function runStrategyLabel(run: EvaluationRun): string {
  return run.strategy_id ?? run.model_id ?? "—";
}

export function runIntervalLabel(run: EvaluationRun): string {
  return run.horizon_label ?? formatResolutionLabel(run.resolution);
}

export function shortRunId(id: string): string {
  return id.length > 10 ? `${id.slice(0, 8)}…` : id;
}

export function isRunOptimized(run: EvaluationRun): boolean {
  if (run.optimizer_enabled === true) {
    return true;
  }
  const dc = run.data_context;
  const m = run.metrics;
  const dcOrM = Boolean(
    dc?.optimized ||
    dc?.optimizer_enabled ||
    dc?.use_optimized_strategy_params ||
    dc?.apply_sweep_winner ||
    m?.optimized ||
    m?.optimizer_enabled ||
    m?.use_optimized_strategy_params ||
    m?.apply_sweep_winner
  );
  if (dcOrM) return true;
  return Boolean(run.optimizer_enabled);
}

export type RunParameterEntry = {
  key: string;
  value: unknown;
};

export function runParametersList(run: EvaluationRun): RunParameterEntry[] {
  const params = run.parameters;
  if (!params || typeof params !== "object") {
    return [];
  }
  return Object.entries(params)
    .filter(([key, value]) => {
      if (key === "algorithm" || key === "strategy_id" || key.startsWith("_")) {
        return false;
      }
      return value !== null && value !== undefined && value !== "";
    })
    .map(([key, value]) => ({ key, value }));
}

export function runParametersSummary(run: EvaluationRun): string {
  const list = runParametersList(run);
  if (list.length === 0) {
    return "—";
  }
  return list
    .map(({ key, value }) => {
      if (typeof value === "boolean") {
        return value ? key : `!${key}`;
      }
      return `${key}: ${value}`;
    })
    .join(", ");
}
