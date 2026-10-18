"use client";

type SeriesPoint = [number, number];

type StrategyDashboardChartsProps = {
  equityCurve: SeriesPoint[];
  spreadCurve: SeriesPoint[];
  zScoreCurve: SeriesPoint[];
  returnPct: number;
  maxDrawdownPct: number;
};

const HEIGHT = 220;
const WIDTH = 640;
const PAD = { top: 16, right: 12, bottom: 28, left: 48 };

function buildPath(points: SeriesPoint[], minY: number, maxY: number): string {
  if (points.length === 0) {
    return "";
  }
  const innerWidth = WIDTH - PAD.left - PAD.right;
  const innerHeight = HEIGHT - PAD.top - PAD.bottom;
  const minX = points[0][0];
  const maxX = points[points.length - 1][0];
  const spanX = maxX - minX || 1;
  const spanY = maxY - minY || 1;
  return points
    .map(([x, y], index) => {
      const px = PAD.left + ((x - minX) / spanX) * innerWidth;
      const py = PAD.top + innerHeight - ((y - minY) / spanY) * innerHeight;
      return `${index === 0 ? "M" : "L"}${px.toFixed(1)},${py.toFixed(1)}`;
    })
    .join(" ");
}

function MiniChart({
  title,
  points,
  stroke,
  zeroLine,
}: {
  title: string;
  points: SeriesPoint[];
  stroke: string;
  zeroLine?: boolean;
}) {
  if (points.length < 2) {
    return (
      <div className="rounded-lg border border-border bg-panel/40 p-3">
        <p className="text-xs font-medium text-muted">{title}</p>
        <p className="mt-2 text-sm text-muted">Not enough data</p>
      </div>
    );
  }
  const values = points.map((point) => point[1]);
  let minY = Math.min(...values);
  let maxY = Math.max(...values);
  if (zeroLine) {
    minY = Math.min(minY, 0);
    maxY = Math.max(maxY, 0);
  }
  const path = buildPath(points, minY, maxY);
  const zeroY =
    PAD.top +
    (HEIGHT - PAD.top - PAD.bottom) -
    ((0 - minY) / (maxY - minY || 1)) * (HEIGHT - PAD.top - PAD.bottom);

  return (
    <div className="rounded-lg border border-border bg-panel/40 p-3">
      <p className="text-xs font-medium text-muted">{title}</p>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="mt-1 w-full" role="img">
        {zeroLine ? (
          <line
            x1={PAD.left}
            x2={WIDTH - PAD.right}
            y1={zeroY}
            y2={zeroY}
            stroke="#475569"
            strokeDasharray="4 4"
          />
        ) : null}
        <path d={path} fill="none" stroke={stroke} strokeWidth="2" />
      </svg>
    </div>
  );
}

export function StrategyDashboardCharts({
  equityCurve,
  spreadCurve,
  zScoreCurve,
  returnPct,
  maxDrawdownPct,
}: StrategyDashboardChartsProps) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-4 text-sm">
        <div>
          <span className="text-muted">Return </span>
          <span className={returnPct >= 0 ? "text-emerald-400" : "text-red-400"}>
            {returnPct.toFixed(2)}%
          </span>
        </div>
        <div>
          <span className="text-muted">Max drawdown </span>
          <span>{maxDrawdownPct.toFixed(2)}%</span>
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <MiniChart title="Equity" points={equityCurve} stroke="#38bdf8" />
        <MiniChart title="Spread %" points={spreadCurve} stroke="#a78bfa" zeroLine />
        <MiniChart title="Z-score" points={zScoreCurve} stroke="#fbbf24" zeroLine />
      </div>
    </div>
  );
}

type FundingBacktestChartsProps = {
  equityCurve: SeriesPoint[];
  fundingCurve: SeriesPoint[];
  returnPct: number;
  maxDrawdownPct: number;
};

export function FundingBacktestCharts({
  equityCurve,
  fundingCurve,
  returnPct,
  maxDrawdownPct,
}: FundingBacktestChartsProps) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-4 text-sm">
        <div>
          <span className="text-muted">Return </span>
          <span className={returnPct >= 0 ? "text-emerald-400" : "text-red-400"}>
            {returnPct.toFixed(2)}%
          </span>
        </div>
        <div>
          <span className="text-muted">Max drawdown </span>
          <span>{maxDrawdownPct.toFixed(2)}%</span>
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <MiniChart title="Equity" points={equityCurve} stroke="#38bdf8" />
        <MiniChart title="Cumulative funding PnL" points={fundingCurve} stroke="#34d399" zeroLine />
      </div>
    </div>
  );
}
