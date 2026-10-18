"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useCallback, useState } from "react";
import { LiveSessionsCharts, mergeWatchedIds } from "@/components/LiveSessionsCharts";
import { LiveTradingPanel } from "@/components/LiveTradingPanel";
import { RiskStatePanel } from "@/components/RiskStatePanel";
import { Page } from "@/components/ui/Page";
import { PageHeader } from "@/components/ui/PageHeader";
import { ErrorState } from "@/components/ui/States";
import { api } from "@/lib/api";

export default function LiveTradingPage() {
  const [focusedJobId, setFocusedJobId] = useState<string | null>(null);
  const [watchedJobIds, setWatchedJobIds] = useState<string[]>([]);
  const authQuery = useQuery({ queryKey: ["auth-status"], queryFn: api.authStatus });

  const handleJobsStarted = useCallback((jobIds: string[]) => {
    if (jobIds.length === 0) {
      return;
    }
    setWatchedJobIds((current) => mergeWatchedIds(current, jobIds));
    setFocusedJobId(jobIds[jobIds.length - 1] ?? null);
  }, []);

  const mergeWatched = useCallback((jobIds: string[]) => {
    setWatchedJobIds((current) => mergeWatchedIds(current, jobIds));
  }, []);

  const hyperliquidReady = authQuery.data?.hyperliquid_wallet_configured === true;
  const nobitexReady = authQuery.data?.api_keys_configured === true;

  return (
    <Page>
      <PageHeader
        eyebrow="Trade"
        title="Live trading"
        description="Run one or many sessions in parallel — combine multi market, multi horizon, and multi strategy (up to 16 jobs). Each job gets its own chart, log stream, and candle feed (Hyperliquid by default)."
        actions={
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                hyperliquidReady || nobitexReady
                  ? "bg-emerald-900/40 text-emerald-200 ring-1 ring-emerald-500/30"
                  : "bg-amber-900/30 text-amber-100 ring-1 ring-amber-500/25"
              }`}
            >
              {authQuery.isLoading
                ? "Checking credentials…"
                : authQuery.isError
                  ? "Credential status unavailable"
                  : hyperliquidReady
                ? "Hyperliquid ready"
                : nobitexReady
                  ? "Nobitex keys configured"
                  : "Paper test ready without keys"}
            </span>
            <Link href="/settings" className="text-accent hover:underline">
              Credentials
            </Link>
          </div>
        }
      />

      {authQuery.isError && (
        <ErrorState title="Could not read credential status" error={authQuery.error} hintAuth={false} />
      )}

      <RiskStatePanel />

      <LiveTradingPanel onJobsStarted={handleJobsStarted} />

      <LiveSessionsCharts
        watchedJobIds={watchedJobIds}
        onWatchedJobIdsChange={setWatchedJobIds}
        onMergeWatchedJobIds={mergeWatched}
        focusedJobId={focusedJobId}
        onFocusJob={setFocusedJobId}
      />
    </Page>
  );
}
