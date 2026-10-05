"use client";

import { Card } from "@/components/ui/Card";
import type { EvaluationRun } from "@/lib/api";
import {
  formatMoney,
  formatResolutionLabel,
  formatReturnPct,
  formatUtcTimestamp,
  returnPctClassName,
} from "@/lib/format";
import { runListMetrics } from "@/lib/runDisplay";

type RunDetailOverviewProps = {
  run: EvaluationRun;
};

export function RunDetailOverview({ run }: RunDetailOverviewProps) {
  const isStrategy = run.run_kind === "strategy_backtest";
  const listed = runListMetrics(run);
  const returnPct = listed.returnPct;
  const directionalAccuracy = run.metrics.directional_accuracy;
  const feeRate = run.metrics.fee_rate;
  const slippageRate = run.metrics.slippage_rate;
  const execution = run.metrics.execution;

  const headline = isStrategy
    ? formatReturnPct(returnPct)
    : typeof directionalAccuracy === "number"
      ? `${(directionalAccuracy * 100).toFixed(1)}% dir. acc.`
      : "—";
  const headlineClass = isStrategy ? returnPctClassName(returnPct) : "text-sky-300";

  const netPnlClass =
    listed.netPnl == null
      ? "text-white"
      : listed.netPnl > 0
        ? "text-emerald-400"
        : listed.netPnl < 0
          ? "text-red-400"
          : "text-muted";

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      <section className="rounded-xl border border-border bg-gradient-to-br from-panel to-surface p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-muted text-xs uppercase tracking-wide">Primary metric</p>
            <p className={`mt-1 text-4xl font-semibold tabular-nums ${headlineClass}`}>{headline}</p>
            <p className="text-muted mt-2 text-sm">
              {isStrategy ? "Total return over the backtest window" : "Headline metric for this run"}
            </p>
          </div>
          <span className={`badge ${isStrategy ? "badge-strategy" : "badge-model"}`}>
            {isStrategy ? "Strategy" : "Model"}
          </span>
        </div>
        <dl className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 text-sm">
          {isStrategy && listed.trades != null && (
            <MetricTile label="Trades" value={String(listed.trades)} />
          )}
          {typeof run.metrics.initial_cash === "number" && (
            <MetricTile label="Initial cash" value={formatMoney(run.metrics.initial_cash)} />
          )}
          {listed.finalEquity != null && (
            <MetricTile label="Final equity" value={formatMoney(listed.finalEquity)} />
          )}
          {listed.netPnl != null && (
            <div className="rounded-lg border border-border/80 bg-surface/60 px-3 py-2">
              <dt className="text-muted text-xs">Net PnL</dt>
              <dd className={`mt-0.5 font-medium tabular-nums ${netPnlClass}`}>
                {listed.netPnl > 0 ? "+" : ""}
                {formatMoney(listed.netPnl)}
              </dd>
            </div>
          )}
          {listed.totalFees != null && (
            <MetricTile label="Total fees" value={formatMoney(listed.totalFees)} />
          )}
          {listed.bars != null && <MetricTile label="Bars" value={String(listed.bars)} />}
        </dl>
      </section>

      <Card title="Run details">
        <dl className="grid gap-3 text-sm">
          <DetailRow label="Run ID" value={run.id} mono />
          <DetailRow label="Symbol" value={run.symbol ?? "—"} />
          <DetailRow label="Interval" value={formatResolutionLabel(run.resolution)} />
          <DetailRow label="Strategy" value={run.strategy_id ?? "—"} />
          <DetailRow label="Model" value={run.model_id ?? "—"} />
          <DetailRow label="Horizon" value={run.horizon_label ?? "—"} />
          <DetailRow label="Dataset" value={run.dataset_label ?? "—"} />
          {isStrategy && typeof feeRate === "number" && (
            <DetailRow label="Fee rate" value={`${(feeRate * 100).toFixed(3)}%`} />
          )}
          {isStrategy && typeof slippageRate === "number" && slippageRate > 0 && (
            <DetailRow label="Slippage" value={`${(slippageRate * 100).toFixed(3)}%`} />
          )}
          {isStrategy && typeof execution === "string" && (
            <DetailRow label="Execution" value={execution} />
          )}
          <DetailRow label="Recorded" value={formatUtcTimestamp(run.created_at_utc)} />
        </dl>
      </Card>
    </div>
  );
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border/80 bg-surface/60 px-3 py-2">
      <dt className="text-muted text-xs">{label}</dt>
      <dd className="mt-0.5 font-medium text-white tabular-nums">{value}</dd>
    </div>
  );
}

function DetailRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-4 border-b border-border/60 pb-2 last:border-0 last:pb-0">
      <dt className="text-muted shrink-0">{label}</dt>
      <dd
        className={`text-right text-white break-all ${mono ? "font-mono text-xs" : ""}`}
        title={value}
      >
        {value}
      </dd>
    </div>
  );
}
