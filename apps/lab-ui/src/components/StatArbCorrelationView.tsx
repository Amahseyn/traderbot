"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { States } from "@/components/ui/States";

type StatArbCorrelationViewProps = {
  runId?: string;
};

export function StatArbCorrelationView({ runId }: StatArbCorrelationViewProps) {
  const corrQuery = useQuery({
    queryKey: ["pair-correlation", runId],
    queryFn: () => api.pairCorrelation(runId),
  });

  if (corrQuery.isLoading) {
    return <States.Loading label="Loading return correlation analysis…" />;
  }

  if (corrQuery.isError) {
    return <States.Error title="Failed to load correlation matrix" message={String(corrQuery.error)} />;
  }

  const pairs = corrQuery.data?.pairs ?? [];
  const topPositive = pairs.filter((p) => p.correlation > 0).slice(0, 10);
  const topNegative = pairs.filter((p) => p.correlation < 0).sort((a, b) => a.correlation - b.correlation).slice(0, 10);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        {/* Top Positive Correlations */}
        <Card className="overflow-hidden p-0">
          <div className="border-b border-border bg-panel px-4 py-3">
            <h3 className="text-sm font-semibold text-foreground">Highest Positive Return Correlations</h3>
            <p className="mt-0.5 text-xs text-muted">Pairs exhibiting shared macroeconomic & sector drift (r ≥ 0.70)</p>
          </div>
          {topPositive.length === 0 ? (
            <div className="p-6 text-center text-xs text-muted">No positive candidates recorded.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="data w-full text-left text-xs">
                <thead className="border-b border-border bg-surface text-muted">
                  <tr>
                    <th className="px-4 py-2 font-medium">Pair</th>
                    <th className="px-4 py-2 font-medium">Correlation</th>
                    <th className="px-4 py-2 font-medium">Relative Strength</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {topPositive.map((p) => (
                    <tr key={p.id} className="hover:bg-panel-elevated/50">
                      <td className="px-4 py-2.5 font-mono font-medium">{p.pair_id}</td>
                      <td className="px-4 py-2.5 font-mono tabular-nums text-foreground">
                        {p.correlation.toFixed(4)}
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-24 overflow-hidden rounded-full bg-border">
                            <div
                              className="h-full bg-accent"
                              style={{ width: `${Math.max(0, Math.min(100, p.correlation * 100))}%` }}
                            />
                          </div>
                          <span className="text-[11px] font-mono tabular-nums text-muted">
                            {(p.correlation * 100).toFixed(1)}%
                          </span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Negative Correlation Rankings */}
        <Card className="overflow-hidden p-0">
          <div className="border-b border-border bg-panel px-4 py-3">
            <h3 className="text-sm font-semibold text-foreground">Negative Correlation Rankings</h3>
            <p className="mt-0.5 text-xs text-muted">Dollar-neutral hedges and inverse pairs (r ≤ -0.70)</p>
          </div>
          {topNegative.length === 0 ? (
            <div className="p-6 text-center text-xs text-muted">No negative correlation candidates discovered.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="data w-full text-left text-xs">
                <thead className="border-b border-border bg-surface text-muted">
                  <tr>
                    <th className="px-4 py-2 font-medium">Pair</th>
                    <th className="px-4 py-2 font-medium">Correlation</th>
                    <th className="px-4 py-2 font-medium">Inverse Strength</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {topNegative.map((p) => (
                    <tr key={p.id} className="hover:bg-panel-elevated/50">
                      <td className="px-4 py-2.5 font-mono font-medium">{p.pair_id}</td>
                      <td className="px-4 py-2.5 font-mono tabular-nums text-foreground">
                        {p.correlation.toFixed(4)}
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-24 overflow-hidden rounded-full bg-border">
                            <div
                              className="h-full bg-accent"
                              style={{ width: `${Math.max(0, Math.min(100, Math.abs(p.correlation) * 100))}%` }}
                            />
                          </div>
                          <span className="text-[11px] font-mono tabular-nums text-muted">
                            {(Math.abs(p.correlation) * 100).toFixed(1)}%
                          </span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

