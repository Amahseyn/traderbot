"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { States } from "@/components/ui/States";

type StatArbCointegrationViewProps = {
  runId?: string;
};

export function StatArbCointegrationView({ runId }: StatArbCointegrationViewProps) {
  const cointQuery = useQuery({
    queryKey: ["pair-cointegration", runId],
    queryFn: () => api.pairCointegration(runId),
  });

  if (cointQuery.isLoading) {
    return <States.Loading label="Evaluating cointegration regressions & MacKinnon surfaces…" />;
  }

  if (cointQuery.isError) {
    return <States.Error title="Failed to load cointegration results" message={String(cointQuery.error)} />;
  }

  const results = cointQuery.data?.results ?? [];
  const qualified = results.filter((r) => r.qualification_status === "QUALIFIED");
  const rejected = results.filter((r) => r.qualification_status === "REJECTED");

  return (
    <div className="space-y-6">
      {/* Qualification Summary Card */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Card className="p-4">
          <p className="text-xs text-muted">Tested Pairs</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-foreground">
            {results.length}
          </p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-muted">Statistically Qualified</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-positive">
            {qualified.length}
          </p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-muted">Hard Rejected</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-negative">
            {rejected.length}
          </p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-muted">FDR Critical Cutoff</p>
          <p className="mt-1 text-2xl font-semibold font-mono tabular-nums text-accent">
            q ≤ 0.10
          </p>
        </Card>
      </div>

      {/* Econometric Table */}
      <Card className="overflow-hidden p-0">
        <div className="border-b border-border bg-panel px-4 py-3">
          <h3 className="text-sm font-semibold text-foreground">Cointegration Qualification Results</h3>
          <p className="mt-0.5 text-xs text-muted">
            OLS regression residuals tested using exact finite-sample MacKinnon surfaces, continuous OU half-life, and Chow structural break tests.
          </p>
        </div>
        {results.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted">
            No cointegration tests found. Run pair discovery to populate.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="data w-full text-left text-xs">
              <thead className="border-b border-border bg-surface text-muted">
                <tr>
                  <th className="px-4 py-2 font-medium">Pair</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 font-medium">Hedge Ratio (β)</th>
                  <th className="px-4 py-2 font-medium">ADF Stat</th>
                  <th className="px-4 py-2 font-medium">p-value</th>
                  <th className="px-4 py-2 font-medium">Half-Life (bars)</th>
                  <th className="px-4 py-2 font-medium">Rejection Reasons</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {results.map((r) => {
                  const isQual = r.qualification_status === "QUALIFIED";
                  return (
                    <tr key={r.id} className="hover:bg-panel-elevated/50">
                      <td className="px-4 py-2.5 font-mono font-medium text-foreground">{r.pair_id}</td>
                      <td className="px-4 py-2.5">
                        <span
                          className={`rounded px-1.5 py-0.5 font-mono text-[11px] font-semibold ${
                            isQual
                              ? "bg-panel-elevated text-positive"
                              : "bg-panel-elevated text-negative"
                          }`}
                        >
                          {r.qualification_status}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 font-mono tabular-nums">{r.hedge_ratio.toFixed(4)}</td>
                      <td className="px-4 py-2.5 font-mono tabular-nums">{r.adf_statistic.toFixed(3)}</td>
                      <td className="px-4 py-2.5 font-mono tabular-nums">{r.cointegration_pvalue.toFixed(4)}</td>
                      <td className="px-4 py-2.5 font-mono tabular-nums">
                        {r.half_life_bars !== null ? r.half_life_bars.toFixed(1) : "—"}
                      </td>
                      <td className="px-4 py-2.5">
                        {r.rejection_reasons.length === 0 ? (
                          <span className="text-muted">—</span>
                        ) : (
                          <div className="flex flex-wrap gap-1">
                            {r.rejection_reasons.map((reason, idx) => (
                              <span
                                key={idx}
                                className="rounded bg-panel-elevated px-1.5 py-0.5 font-mono text-[10px] text-muted"
                              >
                                {reason}
                              </span>
                            ))}
                          </div>
                        )}
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
