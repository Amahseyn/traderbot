"use client";

import { useMemo } from "react";

export type PairResearchSeries = {
  timestamp: number[];
  primary_close: number[];
  hedge_close: number[];
  z_score: Array<number | null>;
};

type PairResearchChartsProps = {
  series: PairResearchSeries;
  equityCurve: Array<{ timestamp: number; equity: number }>;
  trades: Array<{ timestamp: number; action: string; price: number }>;
};

const WIDTH = 720;
const HEIGHT = 200;
const PAD = { top: 16, right: 12, bottom: 28, left: 52 };

function scaleLinear(domain: [number, number], range: [number, number]) {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const span = d1 - d0 || 1;
  return (value: number) => r0 + ((value - d0) / span) * (r1 - r0);
}

function LineChart({
  title,
  ys,
  ys2,
  label,
  label2,
  markers,
}: {
  title: string;
  ys: number[];
  ys2?: number[];
  label: string;
  label2?: string;
  markers?: Array<{ index: number; action: string }>;
}) {
  const paths = useMemo(() => {
    const innerW = WIDTH - PAD.left - PAD.right;
    const innerH = HEIGHT - PAD.top - PAD.bottom;
    const all = [...ys, ...(ys2 ?? [])];
    const minY = Math.min(...all);
    const maxY = Math.max(...all);
    const xScale = scaleLinear([0, Math.max(ys.length - 1, 1)], [PAD.left, PAD.left + innerW]);
    const yScale = scaleLinear([minY, maxY], [PAD.top + innerH, PAD.top]);
    const line = ys
      .map((value, index) => `${index === 0 ? "M" : "L"}${xScale(index).toFixed(1)},${yScale(value).toFixed(1)}`)
      .join(" ");
    const line2 = ys2
      ? ys2
          .map((value, index) => `${index === 0 ? "M" : "L"}${xScale(index).toFixed(1)},${yScale(value).toFixed(1)}`)
          .join(" ")
      : null;
    return { line, line2, xScale, yScale, minY, maxY };
  }, [ys, ys2]);

  return (
    <div className="rounded-lg border border-border bg-panel/40 p-3">
      <p className="mb-2 text-sm font-medium text-slate-100">{title}</p>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full max-w-full" role="img" aria-label={title}>
        <path d={paths.line} fill="none" stroke="#2563eb" strokeWidth={1.5} />
        {paths.line2 && <path d={paths.line2} fill="none" stroke="#f59e0b" strokeWidth={1.2} />}
        {markers?.map((marker) => (
          <circle
            key={`${marker.index}-${marker.action}`}
            cx={paths.xScale(marker.index)}
            cy={paths.yScale(ys[marker.index] ?? paths.minY)}
            r={4}
            fill={marker.action === "buy" ? "#16a34a" : "#dc2626"}
          />
        ))}
        <text x={PAD.left} y={12} className="fill-slate-400 text-[10px]">
          {label}
          {label2 ? ` · ${label2}` : ""}
        </text>
      </svg>
    </div>
  );
}

export function PairResearchCharts({ series, equityCurve, trades }: PairResearchChartsProps) {
  const zValues = series.z_score.map((value) => (value == null ? 0 : value));
  const tradeMarkers = trades.map((trade) => {
    const index = series.timestamp.indexOf(trade.timestamp);
    return index >= 0 ? { index, action: trade.action } : null;
  }).filter((marker): marker is { index: number; action: string } => marker !== null);

  const equityYs = equityCurve.map((point) => point.equity);

  return (
    <div className="grid gap-4">
      <LineChart
        title="Pair prices"
        ys={series.primary_close}
        ys2={series.hedge_close}
        label="Primary"
        label2="Hedge"
        markers={tradeMarkers}
      />
      <LineChart title="Spread z-score" ys={zValues} label="Z" />
      <LineChart title="Portfolio equity" ys={equityYs} label="Equity" />
    </div>
  );
}
