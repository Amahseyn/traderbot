"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { CoinBeaconStatusCard } from "@/components/CoinBeaconStatusCard";
import { DiscoveryTrendPreview } from "@/components/DiscoveryTrendPreview";
import { JobErrorAlert } from "@/components/JobErrorAlert";
import {
  DiscoveryMacroCards,
  DiscoveryMarketStructureSnippet,
  DiscoveryRankingsBlock,
  DiscoveryRunConfigSummary,
  DiscoveryScreenerPresetTable,
  DiscoverySentimentSnippet,
  DiscoverySummaryStats,
  DiscoveryTrendScannerTable,
} from "@/components/DiscoveryReportSections";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Field, TextInput } from "@/components/ui/Field";
import { api, artifactUrl, withLabAuth } from "@/lib/api";
import {
  DEFAULT_CREDIT_RESERVE,
  estimateDiscoveryCredits,
  TREND_EXCHANGES,
  TREND_SORT_TIMEFRAMES,
} from "@/lib/discoveryCredits";
import {
  HYPERLIQUID_DISCOVERY_RESOLUTIONS,
  parseSymbolList,
  type DiscoveryDataSource,
} from "@/lib/hyperliquidDiscovery";
import type { OpportunityDiscoveryReport } from "@/lib/opportunityDiscoveryLog";
import { parseDiscoveryArtifactPath } from "@/lib/opportunityDiscoveryLog";
import { ErrorState, Skeleton } from "@/components/ui/States";

type OpportunityDiscoveryPanelProps = {
  onJob?: (jobId: string) => void;
  presetMarketSymbols?: string[];
  compact?: boolean;
  showInlineResults?: boolean;
};

export function OpportunityDiscoveryPanel({
  onJob,
  presetMarketSymbols = [],
  compact = false,
  showInlineResults = true,
}: OpportunityDiscoveryPanelProps) {
  const queryClient = useQueryClient();
  const [dataSource, setDataSource] = useState<DiscoveryDataSource>("coinbeacon");
  const [hlSymbols, setHlSymbols] = useState("");
  const [hlMonths, setHlMonths] = useState("6");
  const [hlMaxSymbols, setHlMaxSymbols] = useState("24");
  const [hlMinVolume, setHlMinVolume] = useState("0");
  const [hlEvaluateStrategies, setHlEvaluateStrategies] = useState(false);
  const [hlResolutions, setHlResolutions] = useState<Set<string>>(() => new Set(["60"]));
  const [exchange, setExchange] = useState("binance-futures");
  const [trendSort, setTrendSort] = useState<string>("1d");
  const [trendDir, setTrendDir] = useState("desc");
  const [trendQuote, setTrendQuote] = useState("USDT");
  const [includeContext, setIncludeContext] = useState(true);
  const [detailTopN, setDetailTopN] = useState("12");
  const [creditReserve, setCreditReserve] = useState(String(DEFAULT_CREDIT_RESERVE));
  const [enabledPresets, setEnabledPresets] = useState<Set<string>>(new Set());
  const [presetsInitialized, setPresetsInitialized] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);

  const statusQuery = useQuery({
    queryKey: ["coinbeacon-status"],
    queryFn: () => api.coinbeaconStatus(),
    staleTime: 60_000,
  });

  const presetsQuery = useQuery({
    queryKey: ["coinbeacon-screener-presets"],
    queryFn: () => api.coinbeaconScreenerPresets(),
    enabled: statusQuery.data?.configured === true,
  });

  useEffect(() => {
    const presets = presetsQuery.data?.presets;
    if (presetsInitialized || !Array.isArray(presets) || presets.length === 0) {
      return;
    }
    setPresetsInitialized(true);
    setEnabledPresets(new Set(presets.map((row) => row.id)));
  }, [presetsQuery.data, presetsInitialized]);

  const estimatedCredits = useMemo(
    () =>
      estimateDiscoveryCredits({
        screenerPresetCount: enabledPresets.size,
        includeContext,
        detailTopN: Number(detailTopN) || 0,
      }),
    [enabledPresets.size, includeContext, detailTopN],
  );

  const discoveryMutation = useMutation({
    mutationFn: () => {
      if (dataSource === "hyperliquid") {
        const resolutions = HYPERLIQUID_DISCOVERY_RESOLUTIONS.filter((resolution) =>
          hlResolutions.has(resolution),
        );
        if (resolutions.length === 0) {
          throw new Error("Select at least one timeframe for Hyperliquid discovery.");
        }
        const symbols = parseSymbolList(hlSymbols);
        const body: Record<string, unknown> = {
          scan_kind: hlEvaluateStrategies ? "strategy_screen" : "market_opportunity",
          exchange: "hyperliquid",
          symbols,
          resolutions,
          months: Number(hlMonths) || 6,
          max_symbols: Number(hlMaxSymbols) || 24,
          min_mean_volume_quote: Number(hlMinVolume) || 0,
          evaluate_strategies: hlEvaluateStrategies,
          use_cache: true,
        };
        return api.postJob("opportunity-discovery", body);
      }
      const presetList = Array.from(enabledPresets);
      if (presetList.length === 0) {
        throw new Error("Select at least one screener preset.");
      }
      const body: Record<string, unknown> = {
        scan_kind: "coinbeacon_market",
        exchange,
        trend_sort: trendSort,
        trend_dir: trendDir,
        trend_quote: trendQuote,
        screener_presets: presetList,
        include_context: includeContext,
        detail_top_n: Number(detailTopN),
        credit_reserve: Number(creditReserve) || DEFAULT_CREDIT_RESERVE,
      };
      return api.postJob("opportunity-discovery", body);
    },
    onSuccess: (payload) => {
      setJobId(payload.id);
      onJob?.(payload.id);
      queryClient.invalidateQueries({ queryKey: ["discovery-runs"] });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["coinbeacon-status"] });
    },
  });

  const jobQuery = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.job(jobId!),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status ?? "";
      return status === "queued" || status === "running" ? 2000 : false;
    },
  });

  const artifactPath = useMemo(
    () => parseDiscoveryArtifactPath(jobQuery.data?.log_text ?? ""),
    [jobQuery.data?.log_text],
  );

  const dbRunQuery = useQuery({
    queryKey: ["discovery-run-by-job", jobId],
    queryFn: () => api.discoveryRunByJob(jobId!),
    enabled: Boolean(jobId) && jobQuery.data?.status === "completed",
    retry: false,
  });

  const artifactReportQuery = useQuery({
    queryKey: ["discovery-report-artifact", artifactPath],
    queryFn: async () => {
      const response = await fetch(artifactUrl(artifactPath!), withLabAuth());
      if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
      }
      return (await response.json()) as OpportunityDiscoveryReport;
    },
    enabled: Boolean(artifactPath) && jobQuery.data?.status === "completed" && !dbRunQuery.data?.report,
  });

  const inlineReport = dbRunQuery.data?.report ?? artifactReportQuery.data;

  const togglePreset = (presetId: string) => {
    setEnabledPresets((previous) => {
      const next = new Set(previous);
      if (next.has(presetId)) {
        next.delete(presetId);
      } else {
        next.add(presetId);
      }
      return next;
    });
  };

  const title = compact ? "Market scan" : "Market opportunity discovery";
  const description = compact
    ? "CoinBeacon or Hyperliquid perp scan — rank markets before Custom research."
    : "CoinBeacon (external screeners + trend) or Hyperliquid (Lab OHLC universe, bar metrics, optional strategy matrix).";

  const coinbeaconReady = statusQuery.data?.configured === true;
  const remainingCredits = statusQuery.data?.credits?.remaining;
  const insufficientCredits =
    remainingCredits != null && remainingCredits < estimatedCredits + (Number(creditReserve) || 0);

  const highlightSymbols = useMemo(
    () => presetMarketSymbols.map((symbol) => symbol.toUpperCase()),
    [presetMarketSymbols],
  );

  return (
    <div className="space-y-6">
      {dataSource === "coinbeacon" && <CoinBeaconStatusCard />}

      <Card title={title} description={description}>
        {presetMarketSymbols.length > 0 && (
          <p className="mb-4 rounded-lg border border-accent/30 bg-accent/10 px-3 py-2 text-sm text-slate-200">
            Highlighting markets from Custom research:{" "}
            <span className="font-mono text-xs">{highlightSymbols.join(", ")}</span>
          </p>
        )}
        <Field label="Data source" hint="Hyperliquid uses exported or cached OHLC on the Lab API host (no CoinBeacon credits).">
          <select
            className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm"
            value={dataSource}
            onChange={(event) => setDataSource(event.target.value as DiscoveryDataSource)}
          >
            <option value="coinbeacon">CoinBeacon — Binance USDT perps + macro</option>
            <option value="hyperliquid">Hyperliquid — Lab perp universe + OHLC</option>
          </select>
        </Field>
        {dataSource === "coinbeacon" && !statusQuery.isLoading && !coinbeaconReady && (
          <p className="mb-4 mt-4 rounded-lg border border-amber-900/50 bg-amber-950/30 px-3 py-2 text-sm text-amber-100/90">
            CoinBeacon is not configured on the Lab API. Use Settings → CoinBeacon or repo <code className="text-xs">.env</code>,
            then restart <code className="text-xs">./run-lab-api.sh</code>.
          </p>
        )}
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            discoveryMutation.mutate();
          }}
        >
          {dataSource === "hyperliquid" && (
            <div className="space-y-4">
              <Field
                label="Symbols (optional)"
                hint="Comma-separated bases (e.g. btc, eth). Leave empty to scan the Hyperliquid perp universe (top liquidity)."
              >
                <TextInput
                  value={hlSymbols}
                  onChange={(event) => setHlSymbols(event.target.value)}
                  placeholder="empty = universe scan"
                />
              </Field>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <Field label="History (months)">
                  <TextInput value={hlMonths} onChange={(event) => setHlMonths(event.target.value)} />
                </Field>
                <Field label="Max symbols" hint="After liquidity filter">
                  <TextInput value={hlMaxSymbols} onChange={(event) => setHlMaxSymbols(event.target.value)} />
                </Field>
                <Field label="Min mean quote vol (24h)">
                  <TextInput value={hlMinVolume} onChange={(event) => setHlMinVolume(event.target.value)} />
                </Field>
              </div>
              <Field label="Timeframes" hint="Each symbol × timeframe is scored (market scan) or backtested (strategy screen).">
                <div className="flex flex-wrap gap-2">
                  {HYPERLIQUID_DISCOVERY_RESOLUTIONS.map((resolution) => {
                    const checked = hlResolutions.has(resolution);
                    return (
                      <label
                        key={resolution}
                        className={`flex cursor-pointer items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs ${
                          checked ? "border-accent/50 bg-accent/15 text-white" : "border-border text-muted"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => {
                            setHlResolutions((previous) => {
                              const next = new Set(previous);
                              if (next.has(resolution)) {
                                next.delete(resolution);
                              } else {
                                next.add(resolution);
                              }
                              return next;
                            });
                          }}
                        />
                        {resolution}
                      </label>
                    );
                  })}
                </div>
              </Field>
              <label className="flex items-center gap-2 text-sm text-slate-200">
                <input
                  type="checkbox"
                  checked={hlEvaluateStrategies}
                  onChange={(event) => setHlEvaluateStrategies(event.target.checked)}
                />
                Strategy screen — walk-forward backtest each supported strategy (slower; uses default strategy set when none selected)
              </label>
              <p className="text-xs text-muted">
                Uses <code className="text-white/80">data/</code> CSVs when present; otherwise fetches Hyperliquid history.
                Export symbols on <a className="text-accent hover:underline" href="/data">Data</a> first for faster runs.
              </p>
            </div>
          )}

          {dataSource === "coinbeacon" && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Exchange" hint="GET /api/coinbeacon/trend-scanner">
              <select
                className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm"
                value={exchange}
                onChange={(event) => setExchange(event.target.value)}
              >
                {TREND_EXCHANGES.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </Field>
            <Field label="Rank trend by">
              <select
                className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm"
                value={trendSort}
                onChange={(event) => setTrendSort(event.target.value)}
              >
                {TREND_SORT_TIMEFRAMES.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </Field>
            <Field label="Trend direction">
              <select
                className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm"
                value={trendDir}
                onChange={(event) => setTrendDir(event.target.value)}
              >
                <option value="desc">desc (strongest first)</option>
                <option value="asc">asc</option>
              </select>
            </Field>
            <Field label="Quote">
              <TextInput value={trendQuote} onChange={(event) => setTrendQuote(event.target.value.toUpperCase())} />
            </Field>
            <Field label="Funding detail (top N)" hint="1 credit per unique base">
              <TextInput value={detailTopN} onChange={(event) => setDetailTopN(event.target.value)} />
            </Field>
            <Field label="Credit reserve" hint="Abort if remaining credits fall below this">
              <TextInput value={creditReserve} onChange={(event) => setCreditReserve(event.target.value)} />
            </Field>
          </div>
          )}
          {dataSource === "coinbeacon" && (
          <label className="flex items-center gap-2 text-sm text-slate-200">
            <input
              type="checkbox"
              checked={includeContext}
              onChange={(event) => setIncludeContext(event.target.checked)}
            />
            Macro context (globals, sentiment, structure) — 3 credits
          </label>
          )}
          {dataSource === "coinbeacon" && (
          <p className="text-sm text-muted">
            Estimated job cost: <span className="font-medium text-white">~{estimatedCredits} credits</span>
            {remainingCredits != null && (
              <> · balance {remainingCredits}{insufficientCredits ? " (may be tight with reserve)" : ""}</>
            )}
          </p>
          )}
          {dataSource === "coinbeacon" && (
          <Field
            label="Screener presets"
            hint="GET /api/coinbeacon/screener/presets — 5 credits each."
          >
            {presetsQuery.isLoading && <Skeleton className="h-24 w-full" />}
            {presetsQuery.error && <ErrorState title="Could not load screener presets." error={presetsQuery.error} />}
            {presetsQuery.data?.presets && (
              <div className="max-h-48 space-y-1 overflow-auto rounded-lg border border-border/80 p-2 text-sm">
                {presetsQuery.data.presets.map((preset) => (
                  <label key={preset.id} className="flex cursor-pointer items-start gap-2 py-0.5">
                    <input
                      type="checkbox"
                      checked={enabledPresets.has(preset.id)}
                      onChange={() => togglePreset(preset.id)}
                    />
                    <span>
                      <span className="font-medium text-slate-200">{preset.label}</span>
                      <span className="block text-xs text-muted">{preset.description}</span>
                    </span>
                  </label>
                ))}
              </div>
            )}
            <div className="mt-2 flex flex-wrap gap-2">
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  const ids = presetsQuery.data?.presets?.map((row) => row.id) ?? [];
                  setEnabledPresets(new Set(ids));
                }}
              >
                Select all
              </Button>
              <Button type="button" variant="secondary" onClick={() => setEnabledPresets(new Set())}>
                Clear
              </Button>
            </div>
          </Field>
          )}
          <JobErrorAlert error={discoveryMutation.error} />
          <Button
            type="submit"
            disabled={
              discoveryMutation.isPending ||
              (dataSource === "coinbeacon" && (!coinbeaconReady || enabledPresets.size === 0)) ||
              (dataSource === "hyperliquid" && hlResolutions.size === 0)
            }
          >
            {discoveryMutation.isPending ? "Starting…" : "Run market discovery"}
          </Button>
          <p className="text-xs text-muted">
            POST <code className="text-white/80">/api/jobs/opportunity-discovery</code>. Results stored via{" "}
            <code className="text-white/80">/api/catalog/discovery-runs</code>.
          </p>
        </form>

        {showInlineResults && jobId && jobQuery.data?.status === "running" && (
          <p className="mt-4 text-sm text-muted">Discovery job running… watch the job monitor for progress.</p>
        )}

        {showInlineResults && inlineReport && (
          <div className="mt-6 space-y-4 border-t border-border/60 pt-4">
            <DiscoveryRunConfigSummary report={inlineReport} />
            <DiscoveryMacroCards report={inlineReport} />
            <DiscoverySummaryStats summary={inlineReport.summary} />
            <DiscoverySentimentSnippet report={inlineReport} />
            <DiscoveryMarketStructureSnippet report={inlineReport} />
            <DiscoveryScreenerPresetTable report={inlineReport} />
            <DiscoveryTrendScannerTable report={inlineReport} />
            <DiscoveryRankingsBlock report={inlineReport} highlightSymbols={highlightSymbols} />
          </div>
        )}
        {showInlineResults && (dbRunQuery.isLoading || artifactReportQuery.isLoading) && artifactPath && (
          <Skeleton className="mt-4 h-32 w-full" />
        )}
        {!showInlineResults && jobId && (
          <p className="mt-3 text-xs text-muted">Job started — full report sections appear below once complete.</p>
        )}
      </Card>

      {dataSource === "coinbeacon" && coinbeaconReady && (
        <DiscoveryTrendPreview
          exchange={exchange}
          trendSort={trendSort}
          trendDir={trendDir}
          trendQuote={trendQuote}
        />
      )}
    </div>
  );
}
