"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type PairMarketSummary } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { States } from "@/components/ui/States";

type StatArbDiscoveryViewProps = {
  exchange?: string;
  runId?: string;
};

export function StatArbDiscoveryView({ exchange = "hyperliquid", runId }: StatArbDiscoveryViewProps) {
  const marketsQuery = useQuery({
    queryKey: ["pair-markets", exchange, runId],
    queryFn: () => api.pairMarkets(exchange, runId),
  });

  const candidatesQuery = useQuery({
    queryKey: ["pair-candidates", runId],
    queryFn: () => api.pairCandidates(runId),
  });

  if (marketsQuery.isLoading || candidatesQuery.isLoading) {
    return <States.Loading label="Loading pair discovery & market data…" />;
  }

  if (marketsQuery.isError) {
    return <States.Error title="Failed to load market discovery" message={String(marketsQuery.error)} />;
  }

  const markets: PairMarketSummary | undefined = marketsQuery.data;
  const candidates = candidatesQuery.data?.candidates ?? [];

  const positiveCandidates = candidates.filter((c) => c.candidate_category === "STRONG_POSITIVE");
  const negativeCandidates = candidates.filter((c) => c.candidate_category === "STRONG_NEGATIVE");
  const weakCandidates = candidates.filter((c) => c.candidate_category === "SCREENED_WEAK");

  return (
    <div className="space-y-6">
      {/* Overview Metrics Cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Card className="p-4">
          <p className="text-xs text-muted">Total Markets Scanned</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-foreground">
            {markets?.total_scanned ?? 0}
          </p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-muted">Tradable Universe</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-positive">
            {markets?.tradable_count ?? 0}
          </p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-muted">Rejected Markets</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-negative">
            {markets?.rejected_count ?? 0}
          </p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-muted">Candidate Pairs</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-accent">
            {candidates.length}
          </p>
        </Card>
      </div>

      {/* Candidate Pools Distribution */}
      <Card className="p-4">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted">
          Pre-Screened Candidate Partitioning
        </h3>
        <p className="mt-1 text-xs text-muted">
          Intelligent candidate pools avoid O(M²) combinatorial explosion without discarding negatively correlated hedges.
        </p>
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="rounded-lg border border-border bg-panel p-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-foreground">Strong Positive</span>
              <span className="rounded bg-accent/15 px-1.5 py-0.5 text-xs font-semibold tabular-nums text-accent">
                r ≥ +0.70
              </span>
            </div>
            <p className="mt-2 text-xl font-bold tabular-nums text-foreground">
              {positiveCandidates.length}
            </p>
            <p className="mt-1 text-[11px] text-muted">Classic co-trending cointegration pairs</p>
          </div>

          <div className="rounded-lg border border-border bg-panel p-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-foreground">Strong Negative</span>
              <span className="rounded bg-accent/15 px-1.5 py-0.5 text-xs font-semibold tabular-nums text-accent">
                r ≤ -0.70
              </span>
            </div>
            <p className="mt-2 text-xl font-bold tabular-nums text-foreground">
              {negativeCandidates.length}
            </p>
            <p className="mt-1 text-[11px] text-muted">Negative-beta market-neutral pairs</p>
          </div>

          <div className="rounded-lg border border-border bg-panel p-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-foreground">Screened Weak</span>
              <span className="rounded bg-accent/15 px-1.5 py-0.5 text-xs font-semibold tabular-nums text-accent">
                Var-Ratio
              </span>
            </div>
            <p className="mt-2 text-xl font-bold tabular-nums text-foreground">
              {weakCandidates.length}
            </p>
            <p className="mt-1 text-[11px] text-muted">Variance-ratio filtered moderate pairs</p>
          </div>
        </div>
      </Card>

      {/* Candidate Pairs Table */}
      <Card className="overflow-hidden p-0">
        <div className="border-b border-border bg-panel px-4 py-3">
          <h3 className="text-sm font-semibold text-foreground">Generated Candidate Pairs</h3>
        </div>
        {candidates.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted">
            No candidates generated yet. Trigger a pair discovery run to populate candidates.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="data w-full text-left text-xs">
              <thead className="border-b border-border bg-surface text-muted">
                <tr>
                  <th className="px-4 py-2 font-medium">Pair ID</th>
                  <th className="px-4 py-2 font-medium">Asset A</th>
                  <th className="px-4 py-2 font-medium">Asset B</th>
                  <th className="px-4 py-2 font-medium">Correlation (r)</th>
                  <th className="px-4 py-2 font-medium">Category</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {candidates.slice(0, 20).map((cand) => (
                  <tr key={cand.id} className="hover:bg-panel-elevated/50">
                    <td className="px-4 py-2.5 font-mono font-medium text-foreground">
                      {cand.pair_id}
                    </td>
                    <td className="px-4 py-2.5 font-medium">{cand.symbol_a}</td>
                    <td className="px-4 py-2.5 font-medium">{cand.symbol_b}</td>
                    <td className="px-4 py-2.5 font-mono tabular-nums">
                      {cand.correlation.toFixed(4)}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className="rounded bg-panel-elevated px-2 py-0.5 font-mono text-[11px] text-muted">
                        {cand.candidate_category}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

