"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import {
  FundingBacktestCharts,
  StrategyDashboardCharts,
} from "@/components/StrategyDashboardCharts";
import { StrategyCatalogPerformance } from "@/components/StrategyCatalogPerformance";
import { StrategyExchangeMatrix } from "@/components/StrategyExchangeMatrix";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field } from "@/components/ui/Field";
import { JobErrorAlert } from "@/components/JobErrorAlert";
import { Page } from "@/components/ui/Page";
import { PageHeader } from "@/components/ui/PageHeader";
import { api, type FundingBacktestResult, type PairBacktestResult } from "@/lib/api";

type Exchange = "nobitex" | "hyperliquid";
type FeeRole = "taker" | "maker";

function formatBarTimestamp(timestamp: number): string {
  const date = new Date(timestamp * 1000);
  if (Number.isNaN(date.getTime())) {
    return String(timestamp);
  }
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function appendPairLeg(
  body: Record<string, unknown>,
  leg: "dominant" | "hedge",
  options: { csv: string; src: string; exchange: Exchange },
) {
  const csv = options.csv.trim();
  if (options.exchange === "nobitex" && csv) {
    body[`${leg}_csv`] = csv;
    return;
  }
  body[`${leg}_src`] = options.src.trim();
}

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
  const [exitThreshold, setExitThreshold] = useState(0.5);
  const [initialCash, setInitialCash] = useState(10_000);
  const [maxBars, setMaxBars] = useState(400);
  const [resolution, setResolution] = useState("60");
  const [fundingSrc, setFundingSrc] = useState("btc");
  const [gridSrc, setGridSrc] = useState("btc");
  const [gridDst, setGridDst] = useState("usdt");
  const [gridCsv, setGridCsv] = useState("");

  const pairMutation = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        exchange,
        fee_role: feeRole,
        lookback_period: lookback,
        entry_threshold: entryThreshold,
        exit_threshold: exitThreshold,
        initial_cash: initialCash,
        resolution,
        max_bars: maxBars,
      };
      appendPairLeg(body, "dominant", { csv: dominantCsv, src: dominantSrc, exchange });
      appendPairLeg(body, "hedge", { csv: hedgeCsv, src: hedgeSrc, exchange });
      if (!body.dominant_csv && !body.hedge_csv) {
        body.dst = exchange === "nobitex" ? "rls" : "usdt";
      } else if (exchange === "nobitex") {
        body.dst = "rls";
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
        max_bars: maxBars,
        resolution,
      }),
  });

  const gridMutation = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        exchange,
        fee_role: feeRole,
        resolution,
        max_bars: Math.min(maxBars, 300),
      };
      if (gridCsv.trim()) {
        body.csv = gridCsv.trim();
      } else {
        body.src = gridSrc;
        body.dst = exchange === "nobitex" ? gridDst : "usdt";
      }
      return api.gridBacktest(body);
    },
  });

  const pairResult: PairBacktestResult | undefined = pairMutation.data;
  const fundingResult: FundingBacktestResult | undefined = fundingMutation.data;

  const datasetOptions = useMemo(
    () => (datasetsQuery.data ?? []).map((row) => ({ id: row.id, path: row.repo_path })),
    [datasetsQuery.data],
  );

  const feeHint = catalogQuery.data?.execution_costs?.[exchange]?.[feeRole];

  const handleExchangeChange = (next: Exchange) => {
    setExchange(next);
    pairMutation.reset();
    gridMutation.reset();
    fundingMutation.reset();
  };

  return (
    <Page className="mx-auto max-w-6xl">
      <PageHeader
        eyebrow="Catalog"
        title="Strategy dashboard"
        description="Hummingbot-style pair, grid, and funding paper backtests on public candles (no live orders). Results here are ephemeral — use Custom research to persist runs in the catalog."
      />

      <Card>
        <div className="flex flex-wrap gap-4">
          <Field label="Exchange">
            <select
              className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
              value={exchange}
              onChange={(event) => handleExchangeChange(event.target.value as Exchange)}
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
          ) : catalogQuery.isError ? (
            <p className="self-end text-xs text-amber-400">Could not load fee defaults</p>
          ) : null}
        </div>
      </Card>

      <StrategyCatalogPerformance exchange={exchange} />

      {catalogQuery.data ? (
        <Card>
          <h2 className="text-sm font-semibold text-white">Venue support</h2>
          <p className="mt-1 text-sm text-muted">Which adopted strategies can run on each exchange in this dashboard.</p>
          <div className="mt-4">
            <StrategyExchangeMatrix catalog={catalogQuery.data} />
          </div>
        </Card>
      ) : catalogQuery.isLoading ? (
        <p className="text-sm text-muted">Loading venue support…</p>
      ) : null}

      <Card>
        <h2 className="text-sm font-semibold text-white">Pair trading (stat arb)</h2>
        <p className="mt-1 text-sm text-muted">
          Nobitex: mix catalog CSVs and live <code className="text-xs">src</code> per leg. Hyperliquid: perp long/short
          on public OHLC (e.g. BTC + ETH).
        </p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          {exchange === "nobitex" ? (
            <>
              <Field label="Dominant leg (optional CSV)">
                <select
                  className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
                  value={dominantCsv}
                  onChange={(event) => setDominantCsv(event.target.value)}
                >
                  <option value="">Use live src below</option>
                  {datasetOptions.map((option) => (
                    <option key={option.id} value={option.path}>
                      {option.path}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Hedge leg (optional CSV)">
                <select
                  className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
                  value={hedgeCsv}
                  onChange={(event) => setHedgeCsv(event.target.value)}
                >
                  <option value="">Use live src below</option>
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
              disabled={exchange === "nobitex" && Boolean(dominantCsv)}
            />
          </Field>
          <Field label="Hedge coin (src)">
            <input
              className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
              value={hedgeSrc}
              onChange={(event) => setHedgeSrc(event.target.value)}
              disabled={exchange === "nobitex" && Boolean(hedgeCsv)}
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
          <Field label="Exit z threshold">
            <input
              type="number"
              step="0.1"
              className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
              value={exitThreshold}
              min={0.1}
              onChange={(event) => setExitThreshold(Number(event.target.value))}
            />
          </Field>
          <Field label="Initial cash">
            <input
              type="number"
              className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
              value={initialCash}
              min={100}
              step={100}
              onChange={(event) => setInitialCash(Number(event.target.value))}
            />
          </Field>
          <Field label="Bar resolution (minutes)">
            <input
              className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
              value={resolution}
              onChange={(event) => setResolution(event.target.value)}
            />
          </Field>
          <Field label="Max bars">
            <input
              type="number"
              className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm"
              value={maxBars}
              min={50}
              max={2000}
              onChange={(event) => setMaxBars(Number(event.target.value))}
            />
          </Field>
        </div>
        <div className="mt-4">
          <Button onClick={() => pairMutation.mutate()} disabled={pairMutation.isPending}>
            {pairMutation.isPending ? "Running…" : "Run pair backtest"}
          </Button>
        </div>
        {pairMutation.isError ? (
          <div className="mt-3">
            <JobErrorAlert error={pairMutation.error} />
          </div>
        ) : null}
        {pairResult ? (
          <div className="mt-4 space-y-4">
            <p className="text-sm text-muted">
              {pairResult.exchange} · {pairResult.trade_count} legs · fees {pairResult.total_fees.toFixed(2)}
            </p>
            <StrategyDashboardCharts
              equityCurve={pairResult.equity_curve}
              spreadCurve={pairResult.spread_curve}
              zScoreCurve={pairResult.z_score_curve}
              returnPct={pairResult.return_pct}
              maxDrawdownPct={pairResult.max_drawdown_pct}
            />
            {pairResult.trades.length > 0 ? (
              <div className="overflow-x-auto rounded-xl border border-border">
                <table className="data text-sm">
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Leg</th>
                      <th>Action</th>
                      <th>Price</th>
                      <th>Size</th>
                      <th>Fee</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pairResult.trades.map((trade, index) => (
                      <tr key={`${trade.timestamp}-${index}`}>
                        <td className="whitespace-nowrap text-muted">
                          {formatBarTimestamp(trade.timestamp)}
                        </td>
                        <td>{trade.leg}</td>
                        <td>{trade.action}</td>
                        <td>{trade.price.toFixed(4)}</td>
                        <td>{trade.size.toFixed(6)}</td>
                        <td>{trade.fee.toFixed(4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        ) : null}
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-white">Spot / perp grid</h2>
        <p className="mt-1 text-sm text-muted">Long-only grid on live candles or a catalog CSV; bounds auto-fit from recent range.</p>
        <div className="mt-4 flex flex-wrap gap-4">
          <Field label="Catalog CSV (optional)">
            <select
              className="min-w-[12rem] rounded-md border border-border bg-surface px-3 py-2 text-sm"
              value={gridCsv}
              onChange={(event) => setGridCsv(event.target.value)}
            >
              <option value="">Live src</option>
              {datasetOptions.map((option) => (
                <option key={option.id} value={option.path}>
                  {option.path}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Src">
            <input
              className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
              value={gridSrc}
              onChange={(event) => setGridSrc(event.target.value)}
              disabled={Boolean(gridCsv)}
            />
          </Field>
          {exchange === "nobitex" ? (
            <Field label="Dst">
              <select
                className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
                value={gridDst}
                onChange={(event) => setGridDst(event.target.value)}
                disabled={Boolean(gridCsv)}
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
        {gridMutation.isError ? (
          <div className="mt-3">
            <JobErrorAlert error={gridMutation.error} />
          </div>
        ) : null}
        {gridMutation.data ? (
          <p className="mt-3 text-sm text-muted">
            Return {gridMutation.data.return_pct.toFixed(2)}% · {gridMutation.data.trade_count} trades · fees{" "}
            {gridMutation.data.total_fees.toFixed(2)} · final equity {gridMutation.data.final_equity.toFixed(2)}
          </p>
        ) : null}
      </Card>

      {exchange === "hyperliquid" ? (
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
            <Button onClick={() => fundingMutation.mutate()} disabled={fundingMutation.isPending}>
              {fundingMutation.isPending ? "Running…" : "Run funding backtest"}
            </Button>
          </div>
          {fundingMutation.isError ? (
            <div className="mt-3">
              <JobErrorAlert error={fundingMutation.error} />
            </div>
          ) : null}
          {fundingResult ? (
            <div className="mt-4 space-y-3">
              <p className="text-sm text-muted">
                {fundingResult.src.toUpperCase()} · funding PnL {fundingResult.total_funding_pnl.toFixed(2)} · fees{" "}
                {fundingResult.total_fees.toFixed(2)} · {fundingResult.trade_count} trades
              </p>
              <FundingBacktestCharts
                equityCurve={fundingResult.equity_curve}
                fundingCurve={fundingResult.funding_curve}
                returnPct={fundingResult.return_pct}
                maxDrawdownPct={fundingResult.max_drawdown_pct}
              />
            </div>
          ) : null}
        </Card>
      ) : (
        <Card>
          <h2 className="text-sm font-semibold text-white">Funding carry</h2>
          <p className="mt-1 text-sm text-muted">
            Funding carry is only supported on Hyperliquid. Switch exchange to Hyperliquid to run this backtest.
          </p>
        </Card>
      )}

      <p className="text-sm text-muted">
        Rule-strategy backtests (SMA, RSI, sweeps, compare) live under{" "}
        <Link href="/custom" className="text-accent hover:underline">Custom research</Link> and{" "}
        <Link href="/runs" className="text-accent hover:underline">Runs</Link>. See{" "}
        <code className="text-xs">docs/hummingbot-adoption.md</code> in the repo for evaluation scripts.
      </p>
    </Page>
  );
}
