"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { StrategyDashboardCharts } from "@/components/StrategyDashboardCharts";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { api, type FundingBacktestResult, type PairBacktestResult } from "@/lib/api";

type Exchange = "nobitex" | "hyperliquid";
type FeeRole = "taker" | "maker";

export default function StrategiesDashboardPage() {
  const catalogQuery = useQuery({
    queryKey: ["strategy-exchange-catalog"],
    queryFn: api.strategyExchangeCatalog,
  });
  const datasetsQuery = useQuery({
    queryKey: ["datasets"],
    queryFn: () => api.datasets(100),
  });

  const [exchange, setExchange] = useState<Exchange>("hyperliquid");
  const [feeRole, setFeeRole] = useState<FeeRole>("taker");
  const [dominantSrc, setDominantSrc] = useState("btc");
  const [hedgeSrc, setHedgeSrc] = useState("eth");
  const [dominantCsv, setDominantCsv] = useState("");
  const [hedgeCsv, setHedgeCsv] = useState("");
  const [lookback, setLookback] = useState(60);
  const [entryThreshold, setEntryThreshold] = useState(2.0);
  const [fundingSrc, setFundingSrc] = useState("btc");
  const [gridSrc, setGridSrc] = useState("btc");
  const [gridDst, setGridDst] = useState("usdt");

  const pairMutation = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        exchange,
        fee_role: feeRole,
        lookback_period: lookback,
        entry_threshold: entryThreshold,
        resolution: "60",
        max_bars: 400,
      };
      if (exchange === "nobitex" && dominantCsv && hedgeCsv) {
        body.dominant_csv = dominantCsv;
        body.hedge_csv = hedgeCsv;
      } else {
        body.dominant_src = dominantSrc;
        body.hedge_src = hedgeSrc;
        body.dst = exchange === "nobitex" ? "rls" : "usdt";
      }
      return api.pairBacktest(body);
    },
  });

  const fundingMutation = useMutation({
    mutationFn: () =>
      api.fundingBacktest({
        exchange: "hyperliquid",
        fee_role: feeRole,
        src: fundingSrc,
        max_bars: 400,
      }),
  });

  const gridMutation = useMutation({
    mutationFn: () =>
      api.gridBacktest({
        exchange,
        fee_role: feeRole,
        src: gridSrc,
        dst: exchange === "nobitex" ? gridDst : "usdt",
        resolution: "60",
        max_bars: 300,
      }),
  });

  const pairResult: PairBacktestResult | undefined = pairMutation.data;
  const fundingResult: FundingBacktestResult | undefined = fundingMutation.data;
  const datasetOptions = useMemo(
    () => (datasetsQuery.data ?? []).map((row) => ({ id: row.id, path: row.repo_path })),
    [datasetsQuery.data],
  );

  const feeHint = catalogQuery.data?.execution_costs?.[exchange]?.[feeRole];

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <PageHeader
        title="Strategy dashboard"
        subtitle="Nobitex spot and Hyperliquid perps (public candles / funding only — paper backtests, no live orders)."
      />
      <Card>
        <div className="flex flex-wrap gap-4">
          <Field label="Exchange">
            <select
              className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
              value={exchange}
              onChange={(event) => setExchange(event.target.value as Exchange)}
            >
              <option value="hyperliquid">Hyperliquid (perps)</option>
              <option value="nobitex">Nobitex (spot)</option>
            </select>
          </Field>
          <Field label="Fee tier">
            <select
              className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
              value={feeRole}
              onChange={(event) => setFeeRole(event.target.value as FeeRole)}
            >
              <option value="taker">Taker</option>
              <option value="maker">Maker</option>
            </select>
          </Field>
          {feeHint ? (
            <p className="self-end text-xs text-muted">
              fee {(feeHint.fee_rate * 100).toFixed(3)}% · slip {(feeHint.slippage_rate * 100).toFixed(3)}%
            </p>
          ) : null}
        </div>
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-white">Pair trading (stat arb)</h2>
        <p className="mt-1 text-sm text-muted">
          Nobitex: spot rebalance between two CSVs or live pairs. Hyperliquid: perp long/short legs on
          public OHLC (e.g. BTC + ETH).
        </p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          {exchange === "nobitex" ? (
            <>
              <Field label="Dominant CSV">
                <select
                  className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
                  value={dominantCsv}
                  onChange={(event) => setDominantCsv(event.target.value)}
                >
                  <option value="">Live src or pick CSV…</option>
                  {datasetOptions.map((option) => (
                    <option key={option.id} value={option.path}>
                      {option.path}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Hedge CSV">
                <select
                  className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
                  value={hedgeCsv}
                  onChange={(event) => setHedgeCsv(event.target.value)}
                >
                  <option value="">Live src or pick CSV…</option>
                  {datasetOptions.map((option) => (
                    <option key={option.id} value={option.path}>
                      {option.path}
                    </option>
                  ))}
                </select>
              </Field>
            </>
          ) : null}
          <Field label="Dominant coin (src)">
            <input
              className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
              value={dominantSrc}
              onChange={(event) => setDominantSrc(event.target.value)}
            />
          </Field>
          <Field label="Hedge coin (src)">
            <input
              className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
              value={hedgeSrc}
              onChange={(event) => setHedgeSrc(event.target.value)}
            />
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
          <Button onClick={() => pairMutation.mutate()} disabled={pairMutation.isPending}>
            {pairMutation.isPending ? "Running…" : "Run pair backtest"}
          </Button>
        </div>
        {pairMutation.isError ? (
          <p className="mt-3 text-sm text-red-400">
            {pairMutation.error instanceof Error ? pairMutation.error.message : "Pair backtest failed"}
          </p>
        ) : null}
        {pairResult ? (
          <div className="mt-4">
            <p className="text-sm text-muted">
              {pairResult.exchange} · {pairResult.trade_count} legs · return {pairResult.return_pct.toFixed(2)}%
            </p>
            <StrategyDashboardCharts
              equityCurve={pairResult.equity_curve}
              spreadCurve={pairResult.spread_curve}
              zScoreCurve={pairResult.z_score_curve}
              returnPct={pairResult.return_pct}
              maxDrawdownPct={pairResult.max_drawdown_pct}
            />
          </div>
        ) : null}
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-white">Spot / perp grid</h2>
        <p className="mt-1 text-sm text-muted">Long-only grid on live candles; bounds auto-fit from recent range.</p>
        <div className="mt-4 flex flex-wrap gap-4">
          <Field label="Src">
            <input
              className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
              value={gridSrc}
              onChange={(event) => setGridSrc(event.target.value)}
            />
          </Field>
          {exchange === "nobitex" ? (
            <Field label="Dst">
              <select
                className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
                value={gridDst}
                onChange={(event) => setGridDst(event.target.value)}
              >
                <option value="rls">rls</option>
                <option value="usdt">usdt</option>
              </select>
            </Field>
          ) : null}
          <Button onClick={() => gridMutation.mutate()} disabled={gridMutation.isPending}>
            {gridMutation.isPending ? "Running…" : "Run grid backtest"}
          </Button>
        </div>
        {gridMutation.data ? (
          <p className="mt-3 text-sm text-muted">
            Return {gridMutation.data.return_pct.toFixed(2)}% · {gridMutation.data.trade_count} trades · fees{" "}
            {gridMutation.data.total_fees.toFixed(2)}
          </p>
        ) : null}
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-white">Funding carry (Hyperliquid only)</h2>
        <p className="mt-1 text-sm text-muted">
          Paper short when hourly funding is elevated; uses public funding history (no wallet).
        </p>
        <div className="mt-4 flex flex-wrap items-end gap-4">
          <Field label="Perp coin">
            <input
              className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
              value={fundingSrc}
              onChange={(event) => setFundingSrc(event.target.value)}
            />
          </Field>
          <Button
            onClick={() => fundingMutation.mutate()}
            disabled={fundingMutation.isPending}
          >
            {fundingMutation.isPending ? "Running…" : "Run funding backtest"}
          </Button>
        </div>
        {fundingResult ? (
          <p className="mt-3 text-sm text-muted">
            Return {fundingResult.return_pct.toFixed(2)}% · funding PnL{" "}
            {fundingResult.total_funding_pnl.toFixed(2)} · {fundingResult.trade_count} trades
          </p>
        ) : null}
      </Card>
    </div>
  );
}
