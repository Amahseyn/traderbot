import type { EvaluationRun } from "@/lib/api";
import { formatResolutionLabel, parseReturnPct } from "@/lib/format";

export type RunListMetrics = {
  returnPct: number | null;
  trades: number | null;
  finalEquity: number | null;
  totalFees: number | null;
  bars: number | null;
  netPnl: number | null;
};

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

  const netPnl =
    typeof cashFlow?.net_pnl === "number"
      ? cashFlow.net_pnl
      : finalEquity != null && typeof metrics.initial_cash === "number"
        ? finalEquity - metrics.initial_cash
        : null;

  return {
    returnPct: parseReturnPct(metrics),
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
