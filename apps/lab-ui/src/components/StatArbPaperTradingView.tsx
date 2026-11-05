"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type PairPaperPositionItem } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { States } from "@/components/ui/States";
import { formatCryptoPrice, formatMoney } from "@/lib/format";

export function StatArbPaperTradingView() {
  const queryClient = useQueryClient();
  const [flattenConfirm, setFlattenConfirm] = useState<string | null>(null);

  const positionsQuery = useQuery({
    queryKey: ["pair-paper-positions"],
    queryFn: () => api.pairPaperPositions(50),
    refetchInterval: 5000,
  });

  const flattenMutation = useMutation({
    mutationFn: (pairId?: string) =>
      api.pairEmergencyExit({ pair_id: pairId, reason: "manual_lab_ui_flatten" }),
    onSuccess: () => {
      setFlattenConfirm(null);
      queryClient.invalidateQueries({ queryKey: ["pair-paper-positions"] });
    },
  });

  if (positionsQuery.isLoading) {
    return <States.Loading label="Connecting to simulated paper trading session…" />;
  }

  if (positionsQuery.isError) {
    return <States.Error title="Failed to load paper positions" message={String(positionsQuery.error)} />;
  }

  const active = positionsQuery.data?.active_positions ?? [];
  const history = positionsQuery.data?.history ?? [];

  const totalUnrealizedPnl = active.reduce((acc, p) => acc + p.unrealized_pnl, 0);
  const totalRealizedPnl = history.reduce((acc, p) => acc + p.realized_pnl, 0);
  const totalFees = active.reduce((acc, p) => acc + p.total_fees, 0) + history.reduce((acc, p) => acc + p.total_fees, 0);
  const totalFunding = active.reduce((acc, p) => acc + p.total_funding, 0) + history.reduce((acc, p) => acc + p.total_funding, 0);

  return (
    <div className="space-y-6">
      {/* Portfolio Paper Summary Cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Card className="p-4">
          <p className="text-xs text-muted">Active Pair Positions</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-foreground">{active.length}</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-muted">Unrealized PnL</p>
          <p
            className={`mt-1 text-2xl font-semibold tabular-nums ${
              totalUnrealizedPnl >= 0 ? "text-positive" : "text-negative"
            }`}
          >
            {totalUnrealizedPnl >= 0 ? "+" : ""}
            {formatMoney(totalUnrealizedPnl)}
          </p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-muted">Realized PnL</p>
          <p
            className={`mt-1 text-2xl font-semibold tabular-nums ${
              totalRealizedPnl >= 0 ? "text-positive" : "text-negative"
            }`}
          >
            {totalRealizedPnl >= 0 ? "+" : ""}
            {formatMoney(totalRealizedPnl)}
          </p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-muted">Frictions (Fees / Funding)</p>
          <p className="mt-1 text-2xl font-semibold font-mono tabular-nums text-muted">
            {formatMoney(totalFees)} / {formatMoney(totalFunding)}
          </p>
        </Card>
      </div>

      {/* Emergency Flatten Action Banner */}
      {active.length > 0 && (
        <div className="flex flex-wrap items-center justify-between rounded-lg border border-border bg-panel p-4">
          <div>
            <p className="text-sm font-medium text-foreground">Risk & Emergency Controls</p>
            <p className="text-xs text-muted">
              Trigger audited emergency unwinds for open statistical arbitrage pairs.
            </p>
          </div>
          <div>
            {flattenConfirm === "ALL" ? (
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-negative">Confirm Flatten All?</span>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => flattenMutation.mutate(undefined)}
                  disabled={flattenMutation.isPending}
                >
                  {flattenMutation.isPending ? "Flattening…" : "Yes, Flatten"}
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setFlattenConfirm(null)}
                >
                  Cancel
                </Button>
              </div>
            ) : (
              <Button
                variant="destructive"
                size="sm"
                onClick={() => setFlattenConfirm("ALL")}
              >
                Emergency Flatten All
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Active Positions Table */}
      <Card className="overflow-hidden p-0">
        <div className="border-b border-border bg-panel px-4 py-3">
          <h3 className="text-sm font-semibold text-foreground">Open Pair Positions</h3>
          <p className="mt-0.5 text-xs text-muted">Real-time two-leg tracking and spread mark-to-market.</p>
        </div>
        {active.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted">
            No active paper positions. Running paper simulation will display live legs here.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="data w-full text-left text-xs">
              <thead className="border-b border-border bg-surface text-muted">
                <tr>
                  <th className="px-4 py-2 font-medium">Pair</th>
                  <th className="px-4 py-2 font-medium">Leg A (Dominant)</th>
                  <th className="px-4 py-2 font-medium">Leg B (Hedge)</th>
                  <th className="px-4 py-2 font-medium">Spread / Z-Score</th>
                  <th className="px-4 py-2 font-medium">Unrealized PnL</th>
                  <th className="px-4 py-2 font-medium">Fees / Funding</th>
                  <th className="px-4 py-2 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {active.map((pos) => {
                  const legADir = pos.leg_a_qty >= 0 ? "BUY" : "SELL";
                  const legBDir = pos.leg_b_qty >= 0 ? "BUY" : "SELL";
                  return (
                    <tr key={pos.id} className="hover:bg-panel-elevated/50">
                      <td className="px-4 py-2.5 font-mono font-medium text-foreground">{pos.pair_id}</td>
                      <td className="px-4 py-2.5 font-mono tabular-nums">
                        <span className={legADir === "BUY" ? "text-positive" : "text-negative"}>
                          {legADir} {Math.abs(pos.leg_a_qty).toFixed(3)}
                        </span>{" "}
                        @ {formatCryptoPrice(pos.entry_price_a)}
                      </td>
                      <td className="px-4 py-2.5 font-mono tabular-nums">
                        <span className={legBDir === "BUY" ? "text-positive" : "text-negative"}>
                          {legBDir} {Math.abs(pos.leg_b_qty).toFixed(3)}
                        </span>{" "}
                        @ {formatCryptoPrice(pos.entry_price_b)}
                      </td>
                      <td className="px-4 py-2.5 font-mono tabular-nums">
                        {pos.entry_spread.toFixed(4)}{" "}
                        <span className="text-muted">
                          (z: {pos.entry_z_score !== null && pos.entry_z_score !== undefined ? pos.entry_z_score.toFixed(3) : "—"})
                        </span>
                      </td>
                      <td className="px-4 py-2.5 font-mono tabular-nums">
                        <span className={pos.unrealized_pnl >= 0 ? "text-positive" : "text-negative"}>
                          {pos.unrealized_pnl >= 0 ? "+" : ""}
                          {formatMoney(pos.unrealized_pnl)}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 font-mono tabular-nums text-muted">
                        {formatMoney(pos.total_fees)} / {formatMoney(pos.total_funding)}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <Button
                          variant="destructive"
                          size="xs"
                          onClick={() => flattenMutation.mutate(pos.pair_id)}
                          disabled={flattenMutation.isPending}
                        >
                          Flatten
                        </Button>
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
