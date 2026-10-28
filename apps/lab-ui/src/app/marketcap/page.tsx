"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, MarketCapCoin } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Page } from "@/components/ui/Page";
import { PageHeader } from "@/components/ui/PageHeader";
import { PageSkeleton } from "@/components/ui/States";
import { MarketCapHeader } from "@/components/marketcap/MarketCapHeader";
import { MarketCapTable } from "@/components/marketcap/MarketCapTable";
import { CoinDetailDrawer } from "@/components/marketcap/CoinDetailDrawer";
import { OpportunityDiscoveryPanel } from "@/components/OpportunityDiscoveryPanel";
import { DiscoveryJobResults } from "@/components/DiscoveryJobResults";
import { DiscoveryRunsHistory } from "@/components/DiscoveryRunsHistory";
import { DiscoveryWorkflowIntro } from "@/components/DiscoveryReportSections";
import { JobMonitor } from "@/components/JobMonitor";

type TabId = "all" | "gainers" | "losers" | "hyperliquid" | "discovery";

function MarketCapContent() {
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();

  const initialTab = (searchParams.get("tab") as TabId) || "all";
  const [activeTab, setActiveTab] = useState<TabId>(initialTab);
  const [searchQuery, setSearchQuery] = useState("");
  const [pageSize, setPageSize] = useState<number>(50);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [sortBy, setSortBy] = useState<string>("market_cap");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [selectedCoin, setSelectedCoin] = useState<MarketCapCoin | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Discovery tab state
  const [discoveryJobId, setDiscoveryJobId] = useState<string | null>(null);
  const [discoveryRunId, setDiscoveryRunId] = useState<string | null>(null);

  const presetMarketSymbols = useMemo(() => {
    const raw = searchParams.get("markets");
    if (!raw?.trim()) return [];
    return raw.split(",").map((s) => s.trim()).filter(Boolean);
  }, [searchParams]);

  const highlightSymbols = useMemo(
    () => presetMarketSymbols.map((s) => s.toUpperCase()),
    [presetMarketSymbols],
  );

  // Global macro metrics query
  const { data: globalMetrics, isLoading: isGlobalLoading } = useQuery({
    queryKey: ["marketcap-global"],
    queryFn: () => api.marketCapGlobal(false),
    refetchInterval: 60000,
  });

  // Coins ranking query
  const categoryParam = activeTab === "discovery" ? "all" : activeTab;
  const { data: coinsData, isLoading: isCoinsLoading } = useQuery({
    queryKey: ["marketcap-coins", categoryParam, currentPage, pageSize, searchQuery, sortBy, sortDir],
    queryFn: () =>
      api.marketCapCoins({
        page: currentPage,
        limit: pageSize,
        category: categoryParam,
        search: searchQuery,
        sort_by: sortBy,
        sort_dir: sortDir,
      }),
    refetchInterval: 60000,
  });

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      await api.refreshMarketCap();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["marketcap-global"] }),
        queryClient.invalidateQueries({ queryKey: ["marketcap-coins"] }),
      ]);
    } catch {
      // keep existing cached state on error
    } finally {
      setIsRefreshing(false);
    }
  }, [queryClient]);

  const handleSort = useCallback(
    (column: string) => {
      if (sortBy === column) {
        setSortDir((prev) => (prev === "asc" ? "desc" : "asc"));
      } else {
        setSortBy(column);
        setSortDir("desc");
      }
      setCurrentPage(1);
    },
    [sortBy],
  );

  const coins = coinsData?.coins ?? [];
  const totalCoins = coinsData?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalCoins / pageSize));

  return (
    <Page>
      <PageHeader
        eyebrow="Markets"
        title="Market Capitalization"
        description="Global cryptocurrency rankings, 7-day sparklines, real-time perpetual open interest, and institutional quantitative screener."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Link href="/custom">
              <Button variant="secondary">Custom pipeline</Button>
            </Link>
            <Link href="/optimizer">
              <Button variant="secondary">Optimizer</Button>
            </Link>
          </div>
        }
      />

      {/* Global Macro Statistics Banner */}
      <MarketCapHeader
        metrics={globalMetrics ?? null}
        isLoading={isGlobalLoading}
        isRefreshing={isRefreshing}
        onRefresh={handleRefresh}
      />

      {/* Navigation Tabs Bar */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-border pb-3">
        <div className="flex items-center gap-1 overflow-x-auto no-scrollbar">
          {(
            [
              { id: "all", label: "All Cryptocurrencies" },
              { id: "gainers", label: "Top Gainers" },
              { id: "losers", label: "Top Losers" },
              { id: "hyperliquid", label: "Hyperliquid Perps" },
              { id: "discovery", label: "Screener & Discovery" },
            ] as const
          ).map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => {
                  setActiveTab(tab.id);
                  setCurrentPage(1);
                }}
                className={`rounded-md px-3 py-1.5 text-xs font-semibold whitespace-nowrap transition-colors duration-150 ${
                  isActive
                    ? "bg-accent/15 text-accent border border-accent/30"
                    : "text-muted hover:bg-panel-elevated hover:text-white"
                }`}
              >
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Search input (when not on discovery tab) */}
        {activeTab !== "discovery" && (
          <div className="relative min-w-[220px] sm:w-64">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setCurrentPage(1);
              }}
              placeholder="Search coin or symbol..."
              className="w-full rounded-md border border-border bg-panel py-1.5 pl-8 pr-3 text-xs text-white placeholder-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
            />
            <svg
              className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.35-4.35" />
            </svg>
            {searchQuery && (
              <button
                type="button"
                onClick={() => {
                  setSearchQuery("");
                  setCurrentPage(1);
                }}
                className="absolute right-2 top-2 text-muted hover:text-white"
              >
                ✕
              </button>
            )}
          </div>
        )}
      </div>

      {/* Main View: Market Cap Table vs Screener & Discovery */}
      {activeTab !== "discovery" ? (
        <div className="space-y-4">
          <MarketCapTable
            coins={coins}
            selectedCoin={selectedCoin}
            onSelectCoin={setSelectedCoin}
            sortBy={sortBy}
            sortDir={sortDir}
            onSort={handleSort}
            isLoading={isCoinsLoading}
          />

          {/* Pagination Controls */}
          {totalCoins > 0 && (
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between rounded-lg border border-border bg-panel p-3 text-xs text-muted">
              <div className="flex items-center gap-2">
                <span>Show</span>
                <select
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(Number(e.target.value));
                    setCurrentPage(1);
                  }}
                  className="rounded border border-border bg-panel-elevated py-1 px-2 text-xs text-white focus:outline-none focus:ring-1 focus:ring-accent"
                >
                  <option value={20}>20</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                </select>
                <span>assets per page</span>
                <span className="text-border-bright">•</span>
                <span className="tabular-nums">
                  Showing {(currentPage - 1) * pageSize + 1}–{Math.min(currentPage * pageSize, totalCoins)} of {totalCoins}
                </span>
              </div>

              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  disabled={currentPage <= 1}
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  className="h-7 px-2.5 text-xs"
                >
                  Previous
                </Button>
                <span className="font-mono tabular-nums text-white px-2">
                  Page {currentPage} of {totalPages}
                </span>
                <Button
                  variant="secondary"
                  disabled={currentPage >= totalPages}
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  className="h-7 px-2.5 text-xs"
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </div>
      ) : (
        /* Discovery & Screener tab (incorporating existing /new capabilities) */
        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,22rem)] lg:items-start">
          <div className="space-y-8">
            <section id="discovery" className="scroll-mt-24 space-y-6">
              <DiscoveryWorkflowIntro />
              <OpportunityDiscoveryPanel
                onJob={setDiscoveryJobId}
                showInlineResults={false}
                presetMarketSymbols={presetMarketSymbols}
              />
              <DiscoveryJobResults
                jobId={discoveryJobId}
                highlightSymbols={highlightSymbols}
              />
              <DiscoveryRunsHistory
                selectedRunId={discoveryRunId}
                onSelectRun={(runId, histJobId) => {
                  setDiscoveryRunId(runId);
                  if (runId && histJobId) setDiscoveryJobId(histJobId);
                }}
                highlightSymbols={highlightSymbols}
              />
            </section>
          </div>

          <div className="lg:sticky lg:top-24 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto">
            <JobMonitor
              activeJobId={discoveryJobId}
              onSelectJob={setDiscoveryJobId}
            />
          </div>
        </div>
      )}

      {/* Slide-out Asset Detail Drawer */}
      <CoinDetailDrawer
        coin={selectedCoin}
        onClose={() => setSelectedCoin(null)}
      />
    </Page>
  );
}

export default function MarketCapPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <MarketCapContent />
    </Suspense>
  );
}
