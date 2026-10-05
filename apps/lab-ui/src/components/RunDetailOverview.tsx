"use client";

import { Card } from "@/components/ui/Card";
import type { EvaluationRun } from "@/lib/api";
import {
  formatMoney,
  formatResolutionLabel,
  formatReturnPct,
  formatUtcTimestamp,
  parseReturnPct,
  returnPctClassName,
} from "@/lib/format";

type RunDetailOverviewProps = {
  run: EvaluationRun;
};

export function RunDetailOverview({ run }: RunDetailOverviewProps) {
  const isStrategy = run.run_kind === "strategy_backtest";
  const returnPct = parseReturnPct(run.metrics);
  const directionalAccuracy = run.metrics.directional_accuracy;
  const trades = run.metrics.trades;
  const bars = run.data_context.bars ?? run.metrics.bars;
  const initialCash = run.metrics.initial_cash;
  const finalEquity = run.metrics.final_equity;

  const headline = isStrategy
    ? formatReturnPct(returnPct)
    : typeof directionalAccuracy === "number"
      ? `${(directionalAccuracy * 100).toFixed(1)}% dir. acc.`
      : "—";
  const headlineClass = isStrategy ? returnPctClassName(returnPct) : "text-sky-300";

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      <section className="rounded-xl border border-border bg-gradient-to-br from-panel to-surface p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-muted text-xs uppercase tracking-wide">Primary metric</p>
            <p className={`mt-1 text-4xl font-semibold tabular-nums ${headlineClass}`}>{headline}</p>
            <p className="text-muted mt-2 text-sm">
              {isStrategy ? "Total return over the backtest window" : "Holdout directional accuracy"}
            </p>
          </div>
          <span
            className={`badge ${isStrategy ? "badge-strategy" : "badge-model"}`}
          >
            {isStrategy ? "Strategy" : "ML forecast"}
          </span>
        </div>
        <dl className="mt-6 grid gap-3 sm:grid-cols-3 text-sm">
          {isStrategy && typeof trades === "number" && (
            <MetricTile label="Trades" value={String(trades)} />
          )}
          {typeof initialCash === "number" && (
            <MetricTile label="Initial cash" value={formatMoney(initialCash)} />
          )}
          {typeof finalEquity === "number" && (
            <MetricTile label="Final equity" value={formatMoney(finalEquity)} />
          )}
          {typeof bars === "number" && <MetricTile label="Bars" value={String(bars)} />}
        </dl>
      </section>

      <Card title="Run details">
        <dl className="grid gap-3 text-sm">
          <DetailRow label="Symbol" value={run.symbol ?? "—"} />
          <DetailRow
            label="Interval"
            value={formatResolutionLabel(run.resolution)}
          />
          <DetailRow label="Strategy" value={run.strategy_id ?? "—"} />
          <DetailRow label="Model" value={run.model_id ?? "—"} />
          <DetailRow label="Horizon" value={run.horizon_label ?? "—"} />
          <DetailRow label="Dataset" value={run.dataset_label ?? "—"} />
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

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-b border-border/60 pb-2 last:border-0 last:pb-0">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right text-white">{value}</dd>
    </div>
  );
}
