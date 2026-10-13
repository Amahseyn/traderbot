export type VectorbtMetrics = {
  execution?: string;
  total_return_pct?: number | null;
  sharpe_ratio?: number | null;
  max_drawdown_pct?: number | null;
  win_rate_pct?: number | null;
  profit_factor?: number | null;
  total_trades?: number | null;
  expectancy?: number | null;
  calmar_ratio?: number | null;
};

const VECTORBT_LABELS: { key: keyof VectorbtMetrics; label: string; suffix?: string }[] = [
  { key: "sharpe_ratio", label: "Sharpe" },
  { key: "max_drawdown_pct", label: "Max drawdown", suffix: "%" },
  { key: "win_rate_pct", label: "Win rate", suffix: "%" },
  { key: "profit_factor", label: "Profit factor" },
  { key: "total_trades", label: "Trades (vbt)" },
  { key: "expectancy", label: "Expectancy" },
  { key: "calmar_ratio", label: "Calmar" },
];

export function parseVectorbtMetrics(metrics: Record<string, unknown>): VectorbtMetrics | null {
  const raw = metrics.vectorbt;
  if (!raw || typeof raw !== "object") return null;
  return raw as VectorbtMetrics;
}

export function vectorbtMetricRows(
  vectorbt: VectorbtMetrics,
): { label: string; value: string }[] {
  const rows: { label: string; value: string }[] = [];
  for (const { key, label, suffix } of VECTORBT_LABELS) {
    const value = vectorbt[key];
    if (typeof value !== "number") continue;
    const formatted =
      suffix === "%" ? `${value.toFixed(2)}%` : Number.isInteger(value) ? String(value) : value.toFixed(3);
    rows.push({ label, value: formatted });
  }
  return rows;
}
