"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Card } from "@/components/ui/Card";
import { api, type RunAnalytics } from "@/lib/api";
import { formatDurationMinutes, formatMoney, formatReturnPct, returnPctClassName } from "@/lib/format";

function fixed(value: number | null | undefined, digits = 2, suffix = ""): string {
  return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(digits)}${suffix}` : "—";
}

function signedMoney(value: number | null | undefined): string {
  if (typeof value !== "number") return "—";
  return `${value > 0 ? "+" : ""}${formatMoney(value)}`;
}

function toneClass(value: number | null | undefined): string {
  if (typeof value !== "number" || value === 0) return "text-white";
  return value > 0 ? "text-emerald-400" : "text-red-400";
}

type Tile = { label: string; value: string; hint?: string; className?: string };

function buildTiles(summary: RunAnalytics["summary"]): Tile[] {
  return [
    { label: "Net PnL", value: signedMoney(summary.net_pnl), className: toneClass(summary.net_pnl) },
    { label: "Return", value: formatReturnPct(summary.return_pct), className: returnPctClassName(summary.return_pct) },
    { label: "Round trips", value: String(summary.round_trips), hint: `${summary.fills} fills${summary.open_position ? " · position open" : ""}` },
    { label: "Win rate", value: fixed(summary.win_rate_pct, 1, "%"), hint: `${summary.wins}W / ${summary.losses}L` },
    { label: "Profit factor", value: fixed(summary.profit_factor, 2), hint: "Gross profit ÷ gross loss" },
    { label: "Max drawdown", value: fixed(summary.max_drawdown_pct, 2, "%"), hint: formatMoney(summary.max_drawdown_abs ?? undefined), className: "text-red-400" },
    { label: "Sharpe (per trade)", value: fixed(summary.sharpe_per_trade, 2), hint: "Round-trip returns" },
    { label: "Sortino (per trade)", value: fixed(summary.sortino_per_trade, 2), hint: "Downside deviation only" },
    { label: "Avg win", value: formatMoney(summary.avg_win ?? undefined), className: "text-emerald-400" },
    { label: "Avg loss", value: formatMoney(summary.avg_loss ?? undefined), className: "text-red-400" },
    { label: "Payoff ratio", value: fixed(summary.payoff_ratio, 2), hint: "Avg win ÷ |avg loss|" },
    { label: "Expectancy", value: signedMoney(summary.expectancy), hint: "Mean PnL per trip", className: toneClass(summary.expectancy) },
    { label: "Best / worst trade", value: `${signedMoney(summary.best_trade)} / ${signedMoney(summary.worst_trade)}` },
    { label: "Streaks", value: `${summary.max_win_streak}W / ${summary.max_loss_streak}L`, hint: "Longest consecutive" },
    { label: "Exposure", value: fixed(summary.exposure_pct, 1, "%"), hint: "Time in position (fill span)" },
    { label: "Avg hold", value: summary.avg_hold_seconds == null ? "—" : formatDurationMinutes(Math.round(summary.avg_hold_seconds / 60)) },
    { label: "Recovery factor", value: fixed(summary.recovery_factor, 2), hint: "Net PnL ÷ |max DD|" },
    { label: "Fees paid", value: formatMoney(summary.total_fees ?? undefined) },
  ];
}

function LineChart({
  values,
  stroke,
  fill,
  format,
  baseline,
}: {
  values: number[];
  stroke: string;
  fill: string;
  format: (value: number) => string;
  baseline?: number;
}) {
  if (values.length < 2) {
    return <p className="text-muted py-10 text-center text-sm">Not enough points to chart.</p>;
  }
  const width = 600;
  const height = 180;
  const min = Math.min(...values, baseline ?? Infinity);
  const max = Math.max(...values, baseline ?? -Infinity);
  const span = max - min || 1;
  const x = (index: number) => (index / (values.length - 1)) * width;
  const y = (value: number) => height - ((value - min) / span) * height;
  const line = values.map((value, index) => `${index === 0 ? "M" : "L"}${x(index).toFixed(1)},${y(value).toFixed(1)}`).join(" ");
  const area = `${line} L${width},${height} L0,${height} Z`;
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="h-56 w-full sm:h-64" role="img">
        {baseline != null && (
          <line x1={0} x2={width} y1={y(baseline)} y2={y(baseline)} stroke="currentColor" strokeDasharray="4 4" className="text-border" />
        )}
        <path d={area} fill={fill} />
        <path d={line} fill="none" stroke={stroke} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="text-muted mt-1 flex justify-between text-xs tabular-nums">
        <span>min {format(min)}</span>
        <span>max {format(max)}</span>
      </div>
    </div>
  );
}

function TradePnlBars({ pnls }: { pnls: number[] }) {
  if (pnls.length === 0) {
    return <p className="text-muted py-10 text-center text-sm">No closed round trips.</p>;
  }
  const maxAbs = Math.max(...pnls.map(Math.abs)) || 1;
  const width = 600;
  const height = 180;
  const barWidth = width / pnls.length;
  const mid = height / 2;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="h-44 w-full" role="img">
      <line x1={0} x2={width} y1={mid} y2={mid} stroke="currentColor" className="text-border" />
      {pnls.map((pnl, index) => {
        const barHeight = (Math.abs(pnl) / maxAbs) * (mid - 2);
        return (
          <rect
            key={index}
            x={index * barWidth + barWidth * 0.1}
            width={Math.max(barWidth * 0.8, 0.5)}
            y={pnl >= 0 ? mid - barHeight : mid}
            height={barHeight}
            fill={pnl >= 0 ? "rgb(52 211 153)" : "rgb(248 113 113)"}
          />
        );
      })}
    </svg>
  );
}

export function RunAnalyticsPanel({ runId }: { runId: string }) {
  const query = useQuery({ queryKey: ["run-analytics", runId], queryFn: () => api.runAnalytics(runId) });

  if (query.isLoading) {
    return <div className="h-64 animate-pulse rounded-xl bg-panel" />;
  }
  if (query.isError || !query.data) {
    return (
      <Card title="Performance analytics">
        <p className="text-sm text-red-400">
          Could not load analytics{query.error instanceof Error ? `: ${query.error.message}` : "."}
        </p>
      </Card>
    );
  }
  const data = query.data;
  if (data.summary.fills === 0) {
    return (
      <Card title="Performance analytics">
        <p className="text-muted text-sm">This run recorded no trade log, so trade-level analytics are unavailable.</p>
      </Card>
    );
  }
  const tiles = buildTiles(data.summary);
  const pnls = data.trade_pnls.map((trip) => trip.pnl ?? 0);
  return (
    <div className="space-y-4">
      <Card
        title="Performance analytics"
        description="Computed from the recorded fills: round trips are flat → open → flat cycles, PnL includes fees."
      >
        <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          {tiles.map((tile) => (
            <div key={tile.label} className="rounded-lg border border-border/80 bg-surface/60 px-3 py-2">
              <dt className="text-muted text-xs">{tile.label}</dt>
              <dd className={`mt-0.5 font-medium tabular-nums ${tile.className ?? "text-white"}`}>{tile.value}</dd>
              {tile.hint && <p className="text-muted mt-0.5 truncate text-[11px]">{tile.hint}</p>}
            </div>
          ))}
        </dl>
        {data.by_side.length > 0 && (
          <div className="mt-4 overflow-x-auto">
            <table className="data text-xs">
              <thead>
                <tr>
                  <th>Side</th>
                  <th className="text-right">Trips</th>
                  <th className="text-right">Wins</th>
                  <th className="text-right">Win rate</th>
                  <th className="text-right">Net PnL</th>
                </tr>
              </thead>
              <tbody>
                {data.by_side.map((side) => (
                  <tr key={side.side}>
                    <td className="capitalize">{side.side}</td>
                    <td className="text-right tabular-nums">{side.trades}</td>
                    <td className="text-right tabular-nums">{side.wins}</td>
                    <td className="text-right tabular-nums">{fixed(side.win_rate_pct, 1, "%")}</td>
                    <td className={`text-right tabular-nums ${toneClass(side.net_pnl)}`}>{signedMoney(side.net_pnl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <PerformanceChartCard data={data} pnls={pnls} />
    </div>
  );
}

type ChartTab = "equity" | "drawdown" | "trips";

const CHART_TABS: { id: ChartTab; label: string; description: string }[] = [
  { id: "equity", label: "Equity", description: "Portfolio equity after each fill (dashed line = starting cash)." },
  { id: "drawdown", label: "Drawdown", description: "Percent below the running equity peak." },
  { id: "trips", label: "Trip PnL", description: "PnL of each closed round trip, in order." },
];

/** One large chart with segmented tabs (layout pattern inspired by the MIT Black Dashboard theme). */
function PerformanceChartCard({ data, pnls }: { data: RunAnalytics; pnls: number[] }) {
  const [tab, setTab] = useState<ChartTab>("equity");
  const active = CHART_TABS.find((item) => item.id === tab) ?? CHART_TABS[0];
  return (
    <Card
      title="Performance"
      description={active.description}
      actions={
        <div role="tablist" className="flex gap-1 rounded-lg border border-border bg-surface p-0.5 text-xs">
          {CHART_TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={tab === item.id}
              className={`rounded-md px-2.5 py-1 transition ${
                tab === item.id ? "bg-accent/25 text-white" : "text-muted hover:text-white"
              }`}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
      }
    >
      {tab === "equity" && (
        <LineChart
          values={data.equity_curve.map((point) => point.equity)}
          stroke="rgb(56 189 248)"
          fill="rgba(56,189,248,0.12)"
          format={(value) => formatMoney(value)}
          baseline={data.summary.initial_cash ?? undefined}
        />
      )}
      {tab === "drawdown" && (
        <LineChart
          values={data.drawdown_curve.map((point) => point.drawdown_pct ?? 0)}
          stroke="rgb(248 113 113)"
          fill="rgba(248,113,113,0.15)"
          format={(value) => `${value.toFixed(2)}%`}
          baseline={0}
        />
      )}
      {tab === "trips" && <TradePnlBars pnls={pnls} />}
    </Card>
  );
}
