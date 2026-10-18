"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card } from "@/components/ui/Card";
import { Field } from "@/components/ui/Field";
import { ErrorState } from "@/components/ui/States";
import {
  api,
  formatApiError,
  type CatalogStrategy,
  type DashboardStats,
  type LiveStrategyRankRow,
} from "@/lib/api";
import { formatReturnPct, returnPctClassName } from "@/lib/format";
import {
  compareByAvgThenBestReturn,
  compareByPreviewReturn,
  isCompleteCatalogStats,
  isCompleteLivePreview,
  isModelDrivenStrategy,
  pickBestMatchByAvgAndMax,
} from "@/lib/strategyPerformance";

type Exchange = "hyperliquid" | "nobitex";

type PerformanceRow = {
  id: string;
  name: string;
  style: string;
  catalogRuns: number;
  catalogBest: number | null;
  catalogAvg: number | null;
  previewReturn: number | null;
  previewDrawdown: number | null;
  previewTrades: number | null;
  sweepReturn: number | null;
  sweepHoldout: number | null;
  rank: number | null;
};

type StrategyStatRow = {
  strategy_id: string;
  n: number;
  best_return: number | null;
  avg_return: number | null;
};

function statsByStrategyId(stats: DashboardStats | undefined): Map<string, StrategyStatRow> {
  const map = new Map<string, StrategyStatRow>();
  const rows = stats?.strategy_catalog_stats ?? stats?.top_strategies ?? [];
  for (const row of rows) {
    map.set(row.strategy_id, row);
  }
  return map;
}

function buildPerformanceRows(
  strategies: CatalogStrategy[],
  stats: DashboardStats | undefined,
  rankById: Map<string, LiveStrategyRankRow>,
): PerformanceRow[] {
  const catalogStats = statsByStrategyId(stats);
  const rows: PerformanceRow[] = strategies.map((strategy) => {
    const catalog = catalogStats.get(strategy.id);
    const live = rankById.get(strategy.id);
    return {
      id: strategy.id,
      name: strategy.name || strategy.id,
      style: strategy.style,
      catalogRuns: catalog?.n ?? 0,
      catalogBest: catalog?.best_return ?? null,
      catalogAvg: catalog?.avg_return ?? null,
      previewReturn: live?.return_pct ?? null,
      previewDrawdown: live?.max_drawdown_pct ?? null,
      previewTrades: live?.trade_count ?? null,
      sweepReturn: live?.stored_sweep_return_pct ?? null,
      sweepHoldout: live?.stored_sweep_holdout_return_pct ?? null,
      rank: live?.rank ?? null,
    };
  });
  return rows;
}

function CatalogResearchTable({
  rows,
  emptyMessage,
  bestMatchId,
}: {
  rows: PerformanceRow[];
  emptyMessage: string;
  bestMatchId: string | null;
}) {
  if (rows.length === 0) {
    return <p className="text-sm text-muted">{emptyMessage}</p>;
  }
  const sorted = [...rows].sort((left, right) =>
    compareByAvgThenBestReturn(
      { avg_return: left.catalogAvg, best_return: left.catalogBest },
      { avg_return: right.catalogAvg, best_return: right.catalogBest },
    ),
  );
  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <table className="data text-sm">
        <thead>
          <tr>
            <th>Strategy</th>
            <th className="text-right">Runs</th>
            <th className="text-right">Avg return</th>
            <th className="text-right">Best return</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={row.id}>
              <td>
                <div className="font-medium text-slate-100">
                  {row.id === bestMatchId ? (
                    <span className="mr-1.5 rounded bg-accent/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent">
                      Best match
                    </span>
                  ) : null}
                  <Link
                    href={`/runs?strategy_id=${encodeURIComponent(row.id)}`}
                    className="hover:text-accent"
                  >
                    {row.name}
                  </Link>
                </div>
                <div className="text-xs text-muted">{row.id}</div>
              </td>
              <td className="text-right tabular-nums text-muted">{row.catalogRuns || "—"}</td>
              <td
                className={`text-right font-mono tabular-nums ${returnPctClassName(row.catalogAvg)}`}
              >
                {formatReturnPct(row.catalogAvg)}
              </td>
              <td
                className={`text-right font-mono tabular-nums ${returnPctClassName(row.catalogBest)}`}
              >
                {formatReturnPct(row.catalogBest)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LivePreviewTable({
  rows,
  emptyMessage,
  bestMatchId,
}: {
  rows: PerformanceRow[];
  emptyMessage: string;
  bestMatchId: string | null;
}) {
  if (rows.length === 0) {
    return <p className="text-sm text-muted">{emptyMessage}</p>;
  }
  const sorted = [...rows].sort((left, right) =>
    compareByPreviewReturn(left.previewReturn, right.previewReturn),
  );
  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <table className="data text-sm">
        <thead>
          <tr>
            <th>Strategy</th>
            <th className="text-right">Preview return</th>
            <th className="text-right">Preview DD</th>
            <th className="text-right">Trades</th>
            <th className="text-right">Sweep best</th>
            <th className="text-right">Holdout</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={row.id}>
              <td>
                <div className="font-medium text-slate-100">
                  {row.id === bestMatchId ? (
                    <span className="mr-1.5 rounded bg-accent/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent">
                      Best match
                    </span>
                  ) : row.rank != null ? (
                    <span className="mr-1.5 text-xs text-muted">#{row.rank}</span>
                  ) : null}
                  <Link
                    href={`/runs?strategy_id=${encodeURIComponent(row.id)}`}
                    className="hover:text-accent"
                  >
                    {row.name}
                  </Link>
                </div>
                <div className="text-xs text-muted">{row.id}</div>
              </td>
              <td
                className={`text-right font-mono tabular-nums ${returnPctClassName(row.previewReturn)}`}
              >
                {formatReturnPct(row.previewReturn)}
              </td>
              <td className="text-right font-mono tabular-nums text-muted">
                {row.previewDrawdown == null ? "—" : `${row.previewDrawdown.toFixed(2)}%`}
              </td>
              <td className="text-right tabular-nums text-muted">
                {row.previewTrades == null ? "—" : row.previewTrades}
              </td>
              <td
                className={`text-right font-mono tabular-nums ${returnPctClassName(row.sweepReturn)}`}
              >
                {formatReturnPct(row.sweepReturn)}
              </td>
              <td
                className={`text-right font-mono tabular-nums ${returnPctClassName(row.sweepHoldout)}`}
              >
                {formatReturnPct(row.sweepHoldout)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function filterCatalogRows(rows: PerformanceRow[], completeOnly: boolean): PerformanceRow[] {
  return rows.filter((row) => {
    if (!completeOnly) {
      return true;
    }
    return isCompleteCatalogStats(row.catalogRuns, row.catalogAvg, row.catalogBest);
  });
}

function filterLiveRows(rows: PerformanceRow[], completeOnly: boolean): PerformanceRow[] {
  return rows.filter((row) => {
    if (!completeOnly) {
      return true;
    }
    return isCompleteLivePreview(row.previewReturn);
  });
}

type StrategyCatalogPerformanceProps = {
  exchange: Exchange;
};

export function StrategyCatalogPerformance({ exchange }: StrategyCatalogPerformanceProps) {
  const [previewSrc, setPreviewSrc] = useState("btc");
  const [previewDst, setPreviewDst] = useState(exchange === "nobitex" ? "rls" : "usdt");
  const [completeOnly, setCompleteOnly] = useState(true);

  useEffect(() => {
    setPreviewDst(exchange === "nobitex" ? "rls" : "usdt");
  }, [exchange]);
  const [previewResolution, setPreviewResolution] = useState("60");
  const [previewMaxBars, setPreviewMaxBars] = useState(100);

  const strategiesQuery = useQuery({
    queryKey: ["catalog-strategies-implemented"],
    queryFn: () => api.catalogStrategies(true),
  });
  const statsQuery = useQuery({
    queryKey: ["stats"],
    queryFn: api.stats,
  });
  const ranksQuery = useQuery({
    queryKey: [
      "live-strategy-ranks",
      exchange,
      previewSrc,
      previewDst,
      previewResolution,
      previewMaxBars,
    ],
    queryFn: () =>
      api.liveStrategyRanks({
        exchange,
        src: previewSrc,
        dst: previewDst,
        resolution: previewResolution,
        maxBars: previewMaxBars,
      }),
    enabled: Boolean(previewSrc.trim() && previewDst.trim()),
  });

  const rankById = useMemo(() => {
    const map = new Map<string, LiveStrategyRankRow>();
    for (const row of ranksQuery.data?.ranked ?? []) {
      map.set(row.strategy_id, row);
    }
    return map;
  }, [ranksQuery.data]);

  const strategies = strategiesQuery.data ?? [];
  const allRows = useMemo(
    () => buildPerformanceRows(strategies, statsQuery.data, rankById),
    [strategies, statsQuery.data, rankById],
  );

  const catalogBestMatch = useMemo(() => {
    const eligible = filterCatalogRows(allRows, true).map((row) => ({
      id: row.id,
      name: row.name,
      avg_return: row.catalogAvg,
      best_return: row.catalogBest,
    }));
    return pickBestMatchByAvgAndMax(eligible);
  }, [allRows]);

  const liveBestMatch = useMemo(() => {
    const sorted = filterLiveRows(allRows, true).sort((left, right) =>
      compareByPreviewReturn(left.previewReturn, right.previewReturn),
    );
    return sorted[0] ?? null;
  }, [allRows]);

  const modelRows = useMemo(
    () => allRows.filter((row) => isModelDrivenStrategy({ id: row.id, style: row.style })),
    [allRows],
  );
  const ruleRows = useMemo(
    () => allRows.filter((row) => !isModelDrivenStrategy({ id: row.id, style: row.style })),
    [allRows],
  );

  const summary = statsQuery.data?.backtest_summary;

  const renderStrategySections = (rows: PerformanceRow[]) => {
    const catalogRows = filterCatalogRows(rows, completeOnly);
    const liveRows = filterLiveRows(rows, completeOnly);
    const catalogBestId =
      catalogBestMatch && catalogRows.some((row) => row.id === catalogBestMatch.id)
        ? catalogBestMatch.id
        : null;
    const liveBestId =
      liveBestMatch && liveRows.some((row) => row.id === liveBestMatch.id) ? liveBestMatch.id : null;

    return (
      <div className="mt-4 grid gap-6 lg:grid-cols-2">
        <section>
          <h3 className="text-xs font-medium uppercase tracking-wide text-muted">Custom research</h3>
          <p className="mt-1 text-xs text-muted">
            Recorded strategy backtests from completed Custom research runs in the catalog.
          </p>
          <div className="mt-2">
            <CatalogResearchTable
              rows={catalogRows}
              bestMatchId={catalogBestId}
              emptyMessage={
                completeOnly
                  ? "No strategies with completed catalog backtests yet — run Custom research."
                  : "No strategies in the catalog."
              }
            />
          </div>
        </section>
        <section>
          <h3 className="text-xs font-medium uppercase tracking-wide text-muted">Live preview</h3>
          <p className="mt-1 text-xs text-muted">
            Default-param backtests on recent closed candles for the market below.
          </p>
          <div className="mt-2">
            <LivePreviewTable
              rows={liveRows}
              bestMatchId={liveBestId}
              emptyMessage={
                completeOnly
                  ? "No strategies finished a live preview on this market yet."
                  : "No strategies in the catalog."
              }
            />
          </div>
        </section>
      </div>
    );
  };

  return (
    <Card>
      <h2 className="text-sm font-semibold text-white">Strategy &amp; model performance</h2>
      <p className="mt-1 text-sm text-muted">
        Custom research aggregates completed catalog runs (avg and best return). Live preview ranks
        strategies on recent closed candles. Run full compares in{" "}
        <Link href="/custom" className="text-accent hover:underline">Custom research</Link>.
      </p>

      {summary && summary.count > 0 ? (
        <p className="mt-3 text-xs text-muted">
          Catalog: {summary.count} strategy backtests · mean return{" "}
          <span className={returnPctClassName(summary.avg_return)}>
            {formatReturnPct(summary.avg_return)}
          </span>
          · best{" "}
          <span className={returnPctClassName(summary.best_return)}>
            {formatReturnPct(summary.best_return)}
          </span>
        </p>
      ) : null}

      {(catalogBestMatch || liveBestMatch) && (
        <div className="mt-4 flex flex-wrap gap-3 rounded-xl border border-border/80 bg-surface/40 px-4 py-3 text-sm">
          {catalogBestMatch ? (
            <p className="text-muted">
              <span className="font-medium text-slate-200">Best match (Custom research):</span>{" "}
              <Link
                href={`/runs?strategy_id=${encodeURIComponent(catalogBestMatch.id)}`}
                className="text-accent hover:underline"
              >
                {catalogBestMatch.name}
              </Link>
              {" "}
              avg{" "}
              <span className={returnPctClassName(catalogBestMatch.avg_return)}>
                {formatReturnPct(catalogBestMatch.avg_return)}
              </span>
              · best{" "}
              <span className={returnPctClassName(catalogBestMatch.best_return)}>
                {formatReturnPct(catalogBestMatch.best_return)}
              </span>
            </p>
          ) : null}
          {liveBestMatch ? (
            <p className="text-muted">
              <span className="font-medium text-slate-200">Best match (Live preview):</span>{" "}
              <Link
                href={`/runs?strategy_id=${encodeURIComponent(liveBestMatch.id)}`}
                className="text-accent hover:underline"
              >
                {liveBestMatch.name}
              </Link>
              {" "}
              return{" "}
              <span className={returnPctClassName(liveBestMatch.previewReturn)}>
                {formatReturnPct(liveBestMatch.previewReturn)}
              </span>
            </p>
          ) : null}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-end gap-4">
        <Field label="Preview coin (src)">
          <input
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
            value={previewSrc}
            onChange={(event) => setPreviewSrc(event.target.value)}
          />
        </Field>
        <Field label="Quote (dst)">
          <input
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
            value={previewDst}
            onChange={(event) => setPreviewDst(event.target.value)}
          />
        </Field>
        <Field label="Bar resolution (minutes)">
          <input
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
            value={previewResolution}
            onChange={(event) => setPreviewResolution(event.target.value)}
          />
        </Field>
        <Field label="Preview bars">
          <input
            type="number"
            min={20}
            max={300}
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm"
            value={previewMaxBars}
            onChange={(event) => setPreviewMaxBars(Number(event.target.value))}
          />
        </Field>
        <label className="flex cursor-pointer items-center gap-2 pb-2 text-sm text-muted">
          <input
            type="checkbox"
            className="rounded border-border"
            checked={completeOnly}
            onChange={(event) => setCompleteOnly(event.target.checked)}
          />
          Complete only
        </label>
      </div>

      {strategiesQuery.isError ? (
        <ErrorState title="Could not load strategy catalog" error={strategiesQuery.error} hintAuth={false} />
      ) : null}
      {statsQuery.isError ? (
        <ErrorState title="Could not load catalog stats" error={statsQuery.error} hintAuth={false} />
      ) : null}
      {ranksQuery.isError ? (
        <p className="mt-3 text-sm text-amber-400">
          Live preview unavailable ({formatApiError(ranksQuery.error)}).
        </p>
      ) : null}

      {ranksQuery.isSuccess ? (
        <p className="mt-2 text-xs text-muted">
          Live preview on {ranksQuery.data.symbol} · {ranksQuery.data.bars} closed bars ·{" "}
          {exchange}
        </p>
      ) : ranksQuery.isLoading ? (
        <p className="mt-2 text-xs text-muted">Loading live preview ranks…</p>
      ) : null}

      <div className="mt-6 space-y-8">
        <section>
          <h3 className="text-xs font-medium uppercase tracking-wide text-muted">Rule strategies</h3>
          {strategiesQuery.isLoading ? (
            <p className="mt-2 text-sm text-muted">Loading strategies…</p>
          ) : (
            renderStrategySections(ruleRows)
          )}
        </section>

        <section>
          <h3 className="text-xs font-medium uppercase tracking-wide text-muted">
            Models &amp; meta strategies
          </h3>
          <p className="mt-1 text-xs text-muted">
            Online logistic, ensembles, FinRL presets, and other ML-style entries.
          </p>
          {strategiesQuery.isLoading ? (
            <p className="mt-2 text-sm text-muted">Loading strategies…</p>
          ) : (
            renderStrategySections(modelRows)
          )}
        </section>
      </div>
    </Card>
  );
}
