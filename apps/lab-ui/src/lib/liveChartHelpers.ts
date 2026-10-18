import type { OhlcBar } from "@/lib/api";
import type { EquityPoint } from "@/lib/liveLog";

export function barIndexForTimestamp(bars: OhlcBar[], timestamp: number): number {
  let index = bars.findIndex((bar) => Number(bar.timestamp) === timestamp);
  if (index >= 0) {
    return index;
  }
  let best = -1;
  let bestDelta = Number.POSITIVE_INFINITY;
  for (let barIndex = 0; barIndex < bars.length; barIndex += 1) {
    const delta = Math.abs(Number(bars[barIndex].timestamp) - timestamp);
    if (delta < bestDelta) {
      bestDelta = delta;
      best = barIndex;
    }
  }
  return best;
}

export type EquityPlotPoint = {
  x: number;
  equity: number;
  timestamp: number;
};

export function equityPointsToPlot(
  series: EquityPoint[],
  bars: OhlcBar[],
  xForIndex: (index: number) => number,
): EquityPlotPoint[] {
  const points: EquityPlotPoint[] = [];
  for (const point of series) {
    if (point.timestamp <= 1_000_000) {
      continue;
    }
    const index = barIndexForTimestamp(bars, point.timestamp);
    if (index < 0) {
      continue;
    }
    points.push({
      x: xForIndex(index),
      equity: point.equity,
      timestamp: point.timestamp,
    });
  }
  return points;
}

export function polylineFromPoints(points: Array<{ x: number; y: number }>): string {
  if (points.length === 0) {
    return "";
  }
  return points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
}
