"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/States";
import { api } from "@/lib/api";

export function CoinBeaconStatusCard() {
  const statusQuery = useQuery({
    queryKey: ["coinbeacon-status"],
    queryFn: () => api.coinbeaconStatus(),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });

  if (statusQuery.isLoading) {
    return <Skeleton className="h-20 w-full" />;
  }

  const data = statusQuery.data;
  if (!data) {
    return null;
  }

  if (!data.configured) {
    return (
      <Card title="CoinBeacon API" className="border-amber-900/40 bg-amber-950/20">
        <p className="text-sm text-amber-100/90">
          Keys not loaded on the Lab API. Add them in repo <code className="text-xs">.env</code> or{" "}
          <Link href="/settings" className="text-accent hover:underline">Settings → CoinBeacon</Link>, then restart{" "}
          <code className="text-xs">./run-lab-api.sh</code>.
        </p>
      </Card>
    );
  }

  const remaining = data.credits?.remaining;
  const limit = data.credits?.limit;
  const usage = data.usage as Record<string, unknown> | null | undefined;
  const plan = usage && typeof usage.plan === "string" ? usage.plan : null;

  return (
    <Card title="CoinBeacon API" description="Live status from GET /api/coinbeacon/status">
      <dl className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="text-xs text-muted">API keys</dt>
          <dd className="font-medium text-emerald-200">{data.key_count ?? 1} configured</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Daily credits</dt>
          <dd className="font-medium text-white">
            {remaining != null && limit != null ? `${remaining} / ${limit}` : remaining != null ? remaining : "—"}
          </dd>
        </div>
        {plan && (
          <div>
            <dt className="text-xs text-muted">Plan</dt>
            <dd className="font-medium text-white">{plan}</dd>
          </div>
        )}
        <div>
          <dt className="text-xs text-muted">Proxy</dt>
          <dd className="text-xs text-muted">Screener, trend, discovery job</dd>
        </div>
      </dl>
      {data.error && (
        <p className="mt-2 text-xs text-amber-200/90">Usage check: {data.error}</p>
      )}
    </Card>
  );
}
