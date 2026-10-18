"use client";

import Link from "next/link";
import { OpportunityRankTable } from "@/components/OpportunityRankTable";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import type { OpportunityDiscoveryReport } from "@/lib/opportunityDiscoveryLog";

type ScreenerPresetRun = {
  preset?: { id?: string; label?: string };
  meta?: { matched?: number };
};

function perpSentiment(context: OpportunityDiscoveryReport["context"]): Record<string, unknown> | null {
  const sentiment = context?.sentiment;
  if (!sentiment || typeof sentiment !== "object") {
    return null;
  }
  const perp = (sentiment as Record<string, unknown>).PERP;
  return perp && typeof perp === "object" ? (perp as Record<string, unknown>) : null;
}

export function DiscoveryWorkflowIntro() {
  return (
    <Card
      title="Why run discovery?"
      description="A fast market scan before you spend time on backtests or live capital."
    >
      <ol className="list-decimal space-y-2 pl-5 text-sm text-muted">
        <li>
          <span className="text-white/95">Screen the universe</span> — CoinBeacon presets on Binance USDT perps, or a
          Hyperliquid perp scan from Lab OHLC (liquidity, momentum, optional strategy matrix).
        </li>
        <li>
          <span className="text-white/95">Rank a shortlist</span> — merged scores (CoinBeacon trend + screeners, or
          Hyperliquid bar metrics / backtests) with optional macro context on CoinBeacon runs.
        </li>
        <li>
          <span className="text-white/95">Validate in research</span> — pick symbols and open Custom research for
          walk-forward compare, sweeps, and charts before paper or live.
        </li>
      </ol>
      <p className="mt-3 text-xs text-muted">
        Each run is saved in the Lab database (full report JSON) and as{" "}
        <code className="text-white/80">discovery_report.json</code> under results. Re-open past runs in history
        without re-spending API credits.
      </p>
    </Card>
  );
}

export function DiscoveryMacroCards({ report }: { report: OpportunityDiscoveryReport }) {
  const globals = report.context?.globals;
  if (!globals) {
    return null;
  }
  return (
    <dl className="mb-4 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
      <div className="rounded-lg border border-border/70 bg-surface/50 px-3 py-2">
        <dt className="text-xs text-muted">Fear &amp; Greed</dt>
        <dd className="font-semibold text-white">
          {globals.fearGreed?.value ?? "—"}
          {globals.fearGreed?.classification ? ` (${globals.fearGreed.classification})` : ""}
        </dd>
      </div>
      <div className="rounded-lg border border-border/70 bg-surface/50 px-3 py-2">
        <dt className="text-xs text-muted">Avg funding (8h %)</dt>
        <dd className="font-semibold text-white">{globals.avgFunding8hPct ?? "—"}</dd>
      </div>
      <div className="rounded-lg border border-border/70 bg-surface/50 px-3 py-2">
        <dt className="text-xs text-muted">BTC dominance</dt>
        <dd className="font-semibold text-white">
          {globals.btcDominance != null ? `${globals.btcDominance.toFixed(2)}%` : "—"}
        </dd>
      </div>
      {report.credits?.remaining != null && (
        <div className="rounded-lg border border-border/70 bg-surface/50 px-3 py-2">
          <dt className="text-xs text-muted">CoinBeacon credits left</dt>
          <dd className="font-semibold text-white">{report.credits.remaining}</dd>
        </div>
      )}
    </dl>
  );
}

export function DiscoverySummaryStats({ summary }: { summary: OpportunityDiscoveryReport["summary"] }) {
  if (!summary) {
    return null;
  }
  return (
    <dl className="mb-4 grid gap-2 text-sm sm:grid-cols-3">
      <div className="rounded-lg border border-border/70 bg-surface/50 px-3 py-2">
        <dt className="text-xs text-muted">Ranked symbols</dt>
        <dd className="font-semibold text-white">{summary.candidates_evaluated ?? "—"}</dd>
      </div>
      <div className="rounded-lg border border-border/70 bg-surface/50 px-3 py-2">
        <dt className="text-xs text-muted">In shortlist</dt>
        <dd className="font-semibold text-emerald-200">{summary.candidates_eligible ?? "—"}</dd>
      </div>
      <div className="rounded-lg border border-border/70 bg-surface/50 px-3 py-2">
        <dt className="text-xs text-muted">Filtered out</dt>
        <dd className="font-semibold text-amber-100/90">{summary.candidates_rejected ?? "—"}</dd>
      </div>
    </dl>
  );
}

export function DiscoveryScreenerPresetTable({ report }: { report: OpportunityDiscoveryReport }) {
  const presets = (report as OpportunityDiscoveryReport & { screener?: { presets?: ScreenerPresetRun[] } })
    .screener?.presets;
  if (!presets?.length) {
    return null;
  }
  return (
    <Card
      title="Screener presets"
      description="How many symbols matched each CoinBeacon preset in this run."
      className="mb-4"
    >
      <div className="overflow-x-auto">
        <table className="data w-full text-sm">
          <thead>
            <tr>
              <th>Preset</th>
              <th>Matched</th>
            </tr>
          </thead>
          <tbody>
            {presets.map((row, index) => {
              const id = row.preset?.id ?? `preset-${index}`;
              const label = row.preset?.label ?? id;
              return (
                <tr key={id}>
                  <td>
                    <span className="font-medium text-white/95">{label}</span>
                    {label !== id && <span className="ml-2 text-xs text-muted">{id}</span>}
                  </td>
                  <td>{row.meta?.matched ?? "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function DiscoveryRunConfigSummary({ report }: { report: OpportunityDiscoveryReport }) {
  const config = report.config;
  const estimated = report.credits?.estimated_cost;
  if (!config) {
    return null;
  }
  const scanKind = config.scan_kind;
  const hyperliquid =
    scanKind === "market_opportunity" ||
    scanKind === "strategy_screen" ||
    config.exchange === "hyperliquid";
  return (
    <div className="mb-4 rounded-lg border border-border/70 bg-surface/40 px-3 py-2 text-xs text-muted">
      <span className="text-white/90">Run config:</span>{" "}
      {hyperliquid ? (
        <>
          Hyperliquid · {scanKind === "strategy_screen" ? "strategy screen" : "market scan"}
          {Array.isArray(config.resolutions) && <> · TF {config.resolutions.join(", ")}</>}
          {config.months != null && <> · {config.months}mo history</>}
          {config.evaluate_strategies === false && <> · no strategy backtests</>}
        </>
      ) : (
        <>
          {config.exchange ?? "binance-futures"} · trend {config.trend_sort ?? "1d"}{" "}
          {config.trend_dir ?? "desc"} · quote {config.trend_quote ?? "USDT"}
          {Array.isArray(config.screener_presets) && <> · {config.screener_presets.length} screener presets</>}
          {estimated != null && <> · ~{estimated} credits estimated</>}
        </>
      )}
    </div>
  );
}

export function DiscoveryMarketStructureSnippet({ report }: { report: OpportunityDiscoveryReport }) {
  const structure = report.context?.structure;
  if (!structure || typeof structure !== "object") {
    return null;
  }
  const row = structure as Record<string, unknown>;
  const altSeason = row.altSeasonIndex ?? row.alt_season_index;
  const breadth = row.marketBreadth ?? row.market_breadth;
  if (altSeason == null && breadth == null) {
    return null;
  }
  return (
    <div className="mb-4 rounded-lg border border-border/70 bg-surface/50 px-3 py-2 text-sm">
      <p className="text-xs text-muted">Market structure</p>
      <p className="font-medium text-white/95">
        {altSeason != null && <>Alt-season index {String(altSeason)}</>}
        {altSeason != null && breadth != null && " · "}
        {breadth != null && <>Breadth {String(breadth)}</>}
      </p>
    </div>
  );
}

type TrendScannerPayload = {
  exchange?: string;
  sort?: string;
  dir?: string;
  total?: number;
  items?: Array<{
    symbol?: string;
    price?: number;
    scores?: Record<string, { score?: number; direction?: string }>;
  }>;
};

export function DiscoveryTrendScannerTable({ report }: { report: OpportunityDiscoveryReport }) {
  const trend = report.trend_scanner as TrendScannerPayload | undefined;
  const items = trend?.items;
  if (!items?.length) {
    return null;
  }
  const sort = trend?.sort ?? report.config?.trend_sort ?? "1d";
  return (
    <Card
      title="Trend scanner board"
      description={`Raw CoinBeacon trend board (${trend?.exchange ?? "exchange"} · ${sort}) before merge with screeners.`}
      className="mb-4"
    >
      <div className="overflow-x-auto">
        <table className="data w-full text-sm">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Price</th>
              <th>Score ({sort})</th>
              <th>Direction</th>
            </tr>
          </thead>
          <tbody>
            {items.slice(0, 25).map((row, index) => {
              const bucket = row.scores?.[sort];
              return (
                <tr key={row.symbol ?? `t-${index}`}>
                  <td className="font-mono text-xs">{row.symbol ?? "—"}</td>
                  <td>{row.price != null ? row.price.toLocaleString() : "—"}</td>
                  <td>{bucket?.score ?? "—"}</td>
                  <td className="text-muted">{bucket?.direction ?? "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {items.length > 25 && <p className="mt-2 text-xs text-muted">Top 25 of {items.length} shown.</p>}
    </Card>
  );
}

export function DiscoverySentimentSnippet({ report }: { report: OpportunityDiscoveryReport }) {
  const perp = perpSentiment(report.context);
  if (!perp) {
    return null;
  }
  const longPct = perp.longPct ?? perp.long_pct;
  const shortPct = perp.shortPct ?? perp.short_pct;
  return (
    <div className="mb-4 rounded-lg border border-border/70 bg-surface/50 px-3 py-2 text-sm">
      <p className="text-xs text-muted">Perp sentiment (CoinBeacon)</p>
      <p className="font-medium text-white/95">
        Long {longPct != null ? `${longPct}%` : "—"} · Short {shortPct != null ? `${shortPct}%` : "—"}
      </p>
    </div>
  );
}

function customResearchHrefFromReport(report: OpportunityDiscoveryReport): string {
  const bases = (report.ranked ?? [])
    .slice(0, 8)
    .map((row) => (row.base ?? row.symbol_key ?? "").toUpperCase())
    .filter(Boolean);
  if (bases.length === 0) {
    return "/custom";
  }
  return `/custom?markets=${encodeURIComponent(bases.join(","))}`;
}

export function DiscoveryRankingsBlock({
  report,
  highlightSymbols,
}: {
  report: OpportunityDiscoveryReport;
  highlightSymbols?: string[];
}) {
  if (!report.ranked?.length) {
    return (
      <p className="text-sm text-muted">
        No symbols in the merged ranking. Try more screener presets or a different trend sort.
      </p>
    );
  }
  return (
    <>
      <OpportunityRankTable
        ranked={report.ranked}
        rejected={report.rejected}
        scanKind={report.config?.scan_kind}
        coinDetails={report.coin_details}
        highlightSymbols={highlightSymbols}
      />
      <div className="mt-4 flex flex-wrap gap-2 border-t border-border/60 pt-4">
        <Link href={customResearchHrefFromReport(report)}>
          <Button variant="secondary">Validate shortlist in Custom research</Button>
        </Link>
        <Link href="/live">
          <Button variant="ghost">Live sessions</Button>
        </Link>
        <Link href="/data">
          <Button variant="ghost">Export data</Button>
        </Link>
      </div>
    </>
  );
}
