"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card } from "@/components/ui/Card";
import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/States";
import {
  api,
  formatApiError,
  type CatalogStrategy,
  type DashboardStats,
  type LiveStrategyRankRow,
} from "@/lib/api";
import { formatReturnPct, formatWinRate, returnPctClassName } from "@/lib/format";
import {
  filterPerformanceRows,
  isCompleteCatalogStats,
  isCompleteLivePreview,
  isModelDrivenStrategy,
  pickBestMatchByAvgAndMax,
  sortPerformanceRows,
  type PerformanceRow,
  type StrategySortKey,
} from "@/lib/strategyPerformance";

type Exchange = "hyperliquid" | "nobitex";

type StrategyStatRow = {
  strategy_id: string;
  n: number;
  best_return: number | null;
  avg_return: number | null;
  avg_win_rate?: number | null;
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
      summary: strategy.summary,
      style: strategy.style,
      catalogRuns: catalog?.n ?? 0,
      catalogBest: catalog?.best_return ?? null,
      catalogAvg: catalog?.avg_return ?? null,
      catalogWinRate: catalog?.avg_win_rate ?? null,
      previewReturn: live?.return_pct ?? null,
      previewDrawdown: live?.max_drawdown_pct ?? null,
      previewTrades: live?.trade_count ?? null,
      previewWinRate: live?.win_rate_pct ?? null,
      sweepReturn: live?.stored_sweep_return_pct ?? null,
      sweepHoldout: live?.stored_sweep_holdout_return_pct ?? null,
      rank: live?.rank ?? null,
    };
  });
  return rows;
}

const OUTCOME_FILTER_OPTIONS = [
  { value: "", label: "All outcomes" },
  { value: "profitable", label: "Profitable (preview or catalog > 0%)" },
  { value: "positive_catalog", label: "Positive catalog avg (> 0%)" },
  { value: "positive_preview", label: "Positive preview (> 0%)" },
  { value: "loss", label: "Unprofitable (< 0%)" },
];

const WIN_RATE_FILTER_OPTIONS = [
  { value: "", label: "All win rates" },
  { value: "50", label: "≥ 50% win rate" },
  { value: "55", label: "≥ 55% win rate" },
  { value: "60", label: "≥ 60% win rate" },
  { value: "70", label: "≥ 70% win rate" },
];

const STRATEGY_SORT_OPTIONS: { value: StrategySortKey; label: string }[] = [
  { value: "catalog_avg_desc", label: "Catalog avg (high to low)" },
  { value: "catalog_avg_asc", label: "Catalog avg (low to high)" },
  { value: "win_rate_desc", label: "Win rate (high to low)" },
  { value: "preview_return_desc", label: "Preview return (high to low)" },
  { value: "name_asc", label: "Name (A to Z)" },
];

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
  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <table className="data text-sm">
        <thead>
          <tr>
            <th>Strategy</th>
            <th className="text-right">Runs</th>
            <th className="text-right">Avg return</th>
            <th className="text-right">Win rate</th>
            <th className="text-right">Best return</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
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
              <td className="text-right font-mono text-xs tabular-nums text-white">
                {formatWinRate(row.catalogWinRate)}
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
  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <table className="data text-sm">
        <thead>
          <tr>
            <th>Strategy</th>
            <th className="text-right">Preview return</th>
            <th className="text-right">Preview DD</th>
            <th className="text-right">Win rate</th>
            <th className="text-right">Trades</th>
            <th className="text-right">Sweep best</th>
            <th className="text-right">Holdout</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
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
              <td className="text-right font-mono text-xs tabular-nums text-white">
                {formatWinRate(row.previewWinRate)}
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
  const [previewResolution, setPreviewResolution] = useState("60");
  const [previewMaxBars, setPreviewMaxBars] = useState(100);

  const [searchQuery, setSearchQuery] = useState("");
  const [styleFilter, setStyleFilter] = useState("");
  const [outcomeFilter, setOutcomeFilter] = useState("");
  const [winRateFilter, setWinRateFilter] = useState("");
  const [sortBy, setSortBy] = useState<StrategySortKey>("catalog_avg_desc");
  const [completeOnly, setCompleteOnly] = useState(true);

  useEffect(() => {
    setPreviewDst(exchange === "nobitex" ? "rls" : "usdt");
  }, [exchange]);

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
  const availableStyles = useMemo(() => {
    const set = new Set<string>();
    for (const s of strategies) {
      if (s.style?.trim()) set.add(s.style.trim());
    }
    return [...set].sort();
  }, [strategies]);

  const allRows = useMemo(
    () => buildPerformanceRows(strategies, statsQuery.data, rankById),
    [strategies, statsQuery.data, rankById],
  );

  const filteredAndSortedRows = useMemo(() => {
    const filtered = filterPerformanceRows(allRows, {
      query: searchQuery,
      style: styleFilter,
      outcome: outcomeFilter,
      winRate: winRateFilter,
      activity: completeOnly ? "complete_only" : "all",
    });
    return sortPerformanceRows(filtered, sortBy);
  }, [allRows, searchQuery, styleFilter, outcomeFilter, winRateFilter, completeOnly, sortBy]);

  const catalogBestMatch = useMemo(() => {
    const eligible = allRows
      .filter((row) => isCompleteCatalogStats(row.catalogRuns, row.catalogAvg, row.catalogBest))
      .map((row) => ({
        id: row.id,
        name: row.name,
        avg_return: row.catalogAvg,
        best_return: row.catalogBest,
      }));
    return pickBestMatchByAvgAndMax(eligible);
  }, [allRows]);

  const liveBestMatch = useMemo(() => {
    const eligible = allRows
      .filter((row) => isCompleteLivePreview(row.previewReturn))
      .sort((left, right) => (right.previewReturn ?? -Infinity) - (left.previewReturn ?? -Infinity));
    return eligible[0] ?? null;
  }, [allRows]);

  const modelRows = useMemo(
    () => filteredAndSortedRows.filter((row) => isModelDrivenStrategy({ id: row.id, style: row.style })),
    [filteredAndSortedRows],
  );
  const ruleRows = useMemo(
    () => filteredAndSortedRows.filter((row) => !isModelDrivenStrategy({ id: row.id, style: row.style })),
    [filteredAndSortedRows],
  );

  const hasActiveFilters = Boolean(
    searchQuery ||
    styleFilter ||
    outcomeFilter ||
    winRateFilter ||
    sortBy !== "catalog_avg_desc" ||
    !completeOnly
  );

  const activeFilters = useMemo(() => {
    const list: { key: string; label: string; onRemove: () => void }[] = [];
    if (searchQuery.trim()) {
      list.push({
        key: "search",
        label: `Search: "${searchQuery.trim()}"`,
        onRemove: () => setSearchQuery(""),
      });
    }
    if (styleFilter) {
      list.push({
        key: "style",
        label: `Style: ${styleFilter}`,
        onRemove: () => setStyleFilter(""),
      });
    }
    if (outcomeFilter) {
      const opt = OUTCOME_FILTER_OPTIONS.find((o) => o.value === outcomeFilter);
      list.push({
        key: "outcome",
        label: opt ? opt.label : `Outcome: ${outcomeFilter}`,
        onRemove: () => setOutcomeFilter(""),
      });
    }
    if (winRateFilter) {
      list.push({
        key: "win_rate",
        label: `Win rate ≥ ${winRateFilter}%`,
        onRemove: () => setWinRateFilter(""),
      });
    }
    if (sortBy !== "catalog_avg_desc") {
      const opt = STRATEGY_SORT_OPTIONS.find((o) => o.value === sortBy);
      list.push({
        key: "sort",
        label: `Sort: ${opt ? opt.label : sortBy}`,
        onRemove: () => setSortBy("catalog_avg_desc"),
      });
    }
    if (!completeOnly) {
      list.push({
        key: "activity",
        label: "Include zero-run entries",
        onRemove: () => setCompleteOnly(true),
      });
    }
    return list;
  }, [searchQuery, styleFilter, outcomeFilter, winRateFilter, sortBy, completeOnly]);

  const resetFilters = () => {
    setSearchQuery("");
    setStyleFilter("");
    setOutcomeFilter("");
    setWinRateFilter("");
    setSortBy("catalog_avg_desc");
    setCompleteOnly(true);
  };

  const summary = statsQuery.data?.backtest_summary;

  const renderStrategySections = (rows: PerformanceRow[]) => {
    const catalogBestId =
      catalogBestMatch && rows.some((row) => row.id === catalogBestMatch.id)
        ? catalogBestMatch.id
        : null;
    const liveBestId =
      liveBestMatch && rows.some((row) => row.id === liveBestMatch.id) ? liveBestMatch.id : null;

    return (
      <div className="mt-4 grid gap-6 lg:grid-cols-2">
        <section>
          <h3 className="text-xs font-medium uppercase tracking-wide text-muted">Custom research</h3>
          <p className="mt-1 text-xs text-muted">
            Recorded strategy backtests from completed Custom research runs in the catalog.
          </p>
          <div className="mt-2">
            <CatalogResearchTable
              rows={rows}
              bestMatchId={catalogBestId}
              emptyMessage={
                hasActiveFilters
                  ? "No strategies match active filters."
                  : completeOnly
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
              rows={rows}
              bestMatchId={liveBestId}
              emptyMessage={
                hasActiveFilters
                  ? "No strategies match active filters."
                  : completeOnly
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

      {/* Strategy Filters Toolbar */}
      <div className="mt-4 rounded-xl border border-border bg-surface/30 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-muted">
            Filters &amp; sorting
          </span>
          <span className="text-xs text-muted">
            Showing <span className="font-mono text-slate-200">{filteredAndSortedRows.length}</span> of{" "}
            <span className="font-mono text-slate-200">{allRows.length}</span> strategies
          </span>
        </div>

        <div className="mt-3 grid gap-3 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5">
          <Field label="Search">
            <TextInput
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Search by name or ID…"
            />
          </Field>

          <Field label="Style">
            <SelectInput value={styleFilter} onChange={(event) => setStyleFilter(event.target.value)}>
              <option value="">All styles</option>
              {availableStyles.map((style) => (
                <option key={style} value={style}>
                  {style}
                </option>
              ))}
            </SelectInput>
          </Field>

          <Field label="Outcome">
            <SelectInput value={outcomeFilter} onChange={(event) => setOutcomeFilter(event.target.value)}>
              {OUTCOME_FILTER_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </SelectInput>
          </Field>

          <Field label="Win rate">
            <SelectInput value={winRateFilter} onChange={(event) => setWinRateFilter(event.target.value)}>
              {WIN_RATE_FILTER_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </SelectInput>
          </Field>

          <Field label="Sort by">
            <SelectInput
              value={sortBy}
              onChange={(event) => setSortBy(event.target.value as StrategySortKey)}
            >
              {STRATEGY_SORT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </SelectInput>
          </Field>
        </div>

        {activeFilters.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border/50 pt-2.5">
            <span className="text-xs text-muted">Active:</span>
            {activeFilters.map((af) => (
              <span
                key={af.key}
                className="inline-flex items-center gap-1.5 rounded border border-border bg-panel px-2 py-0.5 text-xs text-slate-200"
              >
                <span>{af.label}</span>
                <button
                  type="button"
                  onClick={af.onRemove}
                  className="text-muted hover:text-white"
                  aria-label={`Remove filter: ${af.label}`}
                >
                  ×
                </button>
              </span>
            ))}
            <button
              type="button"
              onClick={resetFilters}
              className="ml-1 text-xs text-accent hover:underline"
            >
              Reset all
            </button>
          </div>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-end gap-4 rounded-xl border border-border/60 bg-surface/20 p-3">
        <Field label="Preview coin (src)">
          <TextInput
            value={previewSrc}
            onChange={(event) => setPreviewSrc(event.target.value)}
          />
        </Field>
        <Field label="Quote (dst)">
          <TextInput
            value={previewDst}
            onChange={(event) => setPreviewDst(event.target.value)}
          />
        </Field>
        <Field label="Bar resolution (minutes)">
          <TextInput
            value={previewResolution}
            onChange={(event) => setPreviewResolution(event.target.value)}
          />
        </Field>
        <Field label="Preview bars">
          <input
            type="number"
            min={20}
            max={300}
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-slate-200"
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
