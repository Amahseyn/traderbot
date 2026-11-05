"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { States } from "@/components/ui/States";

type StatArbRankingsViewProps = {
  exchange?: string;
  timeframe?: string;
  topN?: number;
};

export function StatArbRankingsView({
  exchange = "hyperliquid",
  timeframe = "60",
  topN = 10,
}: StatArbRankingsViewProps) {
  const rankingsQuery = useQuery({
    queryKey: ["pair-rankings", exchange, timeframe, topN],
    queryFn: () => api.pairRankings(exchange, timeframe, topN),
  });

  if (rankingsQuery.isLoading) {
    return <States.Loading label="Loading dynamic pair rankings…" />;
  }

  if (rankingsQuery.isError) {
    return <States.Error title="Failed to load rankings" message={String(rankingsQuery.error)} />;
  }

  const pairs = rankingsQuery.data?.pairs ?? [];

  return (
    <div className="space-y-6">
      <Card className="overflow-hidden p-0">
        <div className="flex flex-wrap items-center justify-between border-b border-border bg-panel px-4 py-3">
          <div>
            <h3 className="text-sm font-semibold text-foreground">Dynamic Statistical Arbitrage Leaderboard</h3>
            <p className="mt-0.5 text-xs text-muted">
              Top {topN} cointegrated pairs ranked by Multi-Factor Quality Score (0–100) with hysteresis retention.
            </p>
          </div>
          <span className="rounded bg-accent/15 px-2.5 py-1 text-xs font-semibold uppercase tracking-wider text-accent">
            {exchange} · {timeframe}m
          </span>
        </div>

        {pairs.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted">
            No qualified pairs ranked. Run a discovery scan across liquid markets.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="data w-full text-left text-xs">
              <thead className="border-b border-border bg-surface text-muted">
                <tr>
                  <th className="px-4 py-2 font-medium">Rank</th>
                  <th className="px-4 py-2 font-medium">Pair</th>
                  <th className="px-4 py-2 font-medium">Quality Score</th>
                  <th className="px-4 py-2 font-medium">Hedge Ratio (β)</th>
                  <th className="px-4 py-2 font-medium">Half-Life</th>
                  <th className="px-4 py-2 font-medium">Stability</th>
                  <th className="px-4 py-2 font-medium">Liquidity</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {pairs.map((p, index) => {
                  const rank = p.ranking_position ?? index + 1;
                  return (
                    <tr key={p.pair_id} className="hover:bg-panel-elevated/50">
                      <td className="px-4 py-2.5 font-mono font-semibold text-foreground">#{rank}</td>
                      <td className="px-4 py-2.5 font-mono font-medium text-foreground">{p.pair_id}</td>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold tabular-nums text-foreground">
                            {p.pair_quality_score.toFixed(1)}
                          </span>
                          <div className="h-1.5 w-16 overflow-hidden rounded-full bg-border">
                            <div
                              className="h-full bg-accent"
                              style={{ width: `${Math.max(0, Math.min(100, p.pair_quality_score))}%` }}
                            />
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-2.5 font-mono tabular-nums">{p.hedge_ratio.toFixed(4)}</td>
                      <td className="px-4 py-2.5 font-mono tabular-nums">
                        {p.half_life_bars !== null ? `${p.half_life_bars.toFixed(1)}b` : "—"}
                      </td>
                      <td className="px-4 py-2.5 font-mono tabular-nums">
                        {(p.stability_score * 100).toFixed(0)}%
                      </td>
                      <td className="px-4 py-2.5 font-mono tabular-nums">
                        {(p.liquidity_score * 100).toFixed(0)}%
                      </td>
                      <td className="px-4 py-2.5">
                        <span className="rounded bg-panel-elevated px-2 py-0.5 font-mono text-[11px] font-medium text-positive">
                          {p.qualification_status}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

