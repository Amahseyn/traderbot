"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card } from "@/components/ui/Card";
import { api } from "@/lib/api";

export function RiskStatePanel() {
  const queryClient = useQueryClient();
  const riskQuery = useQuery({ queryKey: ["risk-state"], queryFn: api.riskState, refetchInterval: 5000 });
  const killMutation = useMutation({
    mutationFn: (enabled: boolean) => api.riskKillSwitch(enabled),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["risk-state"] }),
  });

  const limits = (riskQuery.data?.limits ?? {}) as Record<string, unknown>;
  const halted = Boolean(riskQuery.data?.halted);
  const killSwitch = Boolean(limits.kill_switch);

  return (
    <Card title="Risk manager" description="Live orders pass through these limits (terminal session scope).">
      {riskQuery.isLoading && <p className="text-sm text-muted">Loading risk state…</p>}
      {riskQuery.data && (
        <div className="space-y-3 text-sm">
          <p className={halted ? "text-red-300" : "text-emerald-200"}>
            {halted ? `Halted: ${String(riskQuery.data.halt_reason ?? "unknown")}` : "Trading allowed"}
          </p>
          <ul className="grid gap-1 text-muted sm:grid-cols-2">
            <li>Capital cap: {String(limits.capital_cap ?? "—")}</li>
            <li>Daily loss limit: {String(limits.daily_loss_limit_pct ?? "—")}%</li>
            <li>Max drawdown: {String(limits.max_drawdown_pct ?? "—")}%</li>
            <li>Volatility target: {String(limits.volatility_target_pct ?? "—")}%</li>
          </ul>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={killSwitch}
              onChange={(event) => killMutation.mutate(event.target.checked)}
            />
            Manual kill switch
          </label>
        </div>
      )}
    </Card>
  );
}
