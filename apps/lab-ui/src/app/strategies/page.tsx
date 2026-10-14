"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { StrategyDashboardCharts } from "@/components/StrategyDashboardCharts";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { api, type PairBacktestResult } from "@/lib/api";

export default function StrategiesDashboardPage() {
  const datasetsQuery = useQuery({
    queryKey: ["datasets"],
    queryFn: () => api.datasets(100),
  });
  const [dominantCsv, setDominantCsv] = useState("");
  const [hedgeCsv, setHedgeCsv] = useState("");
  const [lookback, setLookback] = useState(60);
  const [entryThreshold, setEntryThreshold] = useState(2.0);

  const backtestMutation = useMutation({
    mutationFn: () =>
      api.pairBacktest({
        dominant_csv: dominantCsv,
        hedge_csv: hedgeCsv,
        lookback_period: lookback,
        entry_threshold: entryThreshold,
      }),
  });

  const result: PairBacktestResult | undefined = backtestMutation.data;
  const datasetOptions = useMemo(
    () => (datasetsQuery.data ?? []).map((row) => ({ id: row.id, path: row.repo_path })),
    [datasetsQuery.data],
  );

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <PageHeader
        title="Strategy dashboard"
        subtitle="Hummingbot-inspired pair-trading view: spread, z-score, equity, and trades (Nobitex spot, no live orders)."
      />
      <Card>
        <h2 className="text-sm font-semibold text-white">Pair backtest</h2>
        <p className="mt-1 text-sm text-muted">
          Pick two aligned OHLC CSVs (e.g. BTC and ETH vs IRT or USDT). Uses stat-arb z-score logic ported
          from Hummingbot.
        </p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Field label="Dominant CSV path">
            <select
              className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
              value={dominantCsv}
              onChange={(event) => setDominantCsv(event.target.value)}
            >
              <option value="">Select dataset…</option>
              {datasetOptions.map((option) => (
                <option key={option.id} value={option.path}>
                  {option.path}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Hedge CSV path">
            <select
              className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
              value={hedgeCsv}
              onChange={(event) => setHedgeCsv(event.target.value)}
            >
              <option value="">Select dataset…</option>
              {datasetOptions.map((option) => (
                <option key={option.id} value={option.path}>
                  {option.path}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Lookback bars">
            <input
              type="number"
              className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
              value={lookback}
              min={10}
              onChange={(event) => setLookback(Number(event.target.value))}
            />
          </Field>
          <Field label="Entry z threshold">
            <input
              type="number"
              step="0.1"
              className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
              value={entryThreshold}
              min={0.5}
              onChange={(event) => setEntryThreshold(Number(event.target.value))}
            />
          </Field>
        </div>
        <div className="mt-4">
          <Button
            onClick={() => backtestMutation.mutate()}
            disabled={!dominantCsv || !hedgeCsv || backtestMutation.isPending}
          >
            {backtestMutation.isPending ? "Running…" : "Run pair backtest"}
          </Button>
        </div>
        {backtestMutation.isError ? (
          <p className="mt-3 text-sm text-red-400">
            {backtestMutation.error instanceof Error ? backtestMutation.error.message : "Backtest failed"}
          </p>
        ) : null}
      </Card>
      {result ? (
        <Card>
          <h2 className="text-sm font-semibold text-white">Results</h2>
          <p className="mt-1 text-sm text-muted">
            {result.trade_count} legs · fees {result.total_fees.toFixed(2)} · final equity{" "}
            {result.final_equity.toFixed(2)}
          </p>
          <div className="mt-4">
            <StrategyDashboardCharts
              equityCurve={result.equity_curve}
              spreadCurve={result.spread_curve}
              zScoreCurve={result.z_score_curve}
              returnPct={result.return_pct}
              maxDrawdownPct={result.max_drawdown_pct}
            />
          </div>
        </Card>
      ) : null}
    </div>
  );
}
