"use client";

import { MarketCapGlobal } from "@/lib/api";
import { Button } from "@/components/ui/Button";

interface MarketCapHeaderProps {
  metrics: MarketCapGlobal | null;
  isLoading: boolean;
  isRefreshing: boolean;
  onRefresh: () => void;
}

function formatCurrency(val: number | null | undefined): string {
  if (val === null || val === undefined) return "—";
  if (val >= 1e12) return `$${(val / 1e12).toFixed(2)}T`;
  if (val >= 1e9) return `$${(val / 1e9).toFixed(2)}B`;
  if (val >= 1e6) return `$${(val / 1e6).toFixed(2)}M`;
  return `$${val.toLocaleString()}`;
}

export function MarketCapHeader({
  metrics,
  isLoading,
  isRefreshing,
  onRefresh,
}: MarketCapHeaderProps) {
  const capChange = metrics?.market_cap_change_24h_pct ?? 0;
  const isPos = capChange >= 0;

  return (
    <div className="rounded-lg border border-border bg-panel p-4 sm:p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        {/* Metric Cards Grid */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:gap-6">
          {/* Total Market Cap */}
          <div className="space-y-1">
            <div className="text-[11px] font-medium uppercase tracking-wider text-muted">
              Market Capitalization
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-lg font-bold tracking-tight text-white tabular-nums sm:text-xl">
                {isLoading ? "..." : formatCurrency(metrics?.total_market_cap_usd)}
              </span>
              {metrics && (
                <span
                  className={`inline-flex items-center text-xs font-semibold tabular-nums ${
                    isPos ? "text-emerald-400" : "text-rose-400"
                  }`}
                >
                  {isPos ? "+" : ""}
                  {capChange.toFixed(2)}%
                </span>
              )}
            </div>
          </div>

          {/* 24h Volume */}
          <div className="space-y-1">
            <div className="text-[11px] font-medium uppercase tracking-wider text-muted">
              24h Total Volume
            </div>
            <div className="text-lg font-bold tracking-tight text-white tabular-nums sm:text-xl">
              {isLoading ? "..." : formatCurrency(metrics?.total_volume_24h_usd)}
            </div>
          </div>

          {/* Dominance */}
          <div className="space-y-1">
            <div className="text-[11px] font-medium uppercase tracking-wider text-muted">
              Market Dominance
            </div>
            <div className="flex items-center gap-3 text-sm font-semibold tabular-nums text-zinc-200">
              <span>
                <strong className="text-muted font-normal">BTC: </strong>
                {metrics?.btc_dominance_pct ? `${metrics.btc_dominance_pct}%` : "—"}
              </span>
              <span className="text-border-bright">/</span>
              <span>
                <strong className="text-muted font-normal">ETH: </strong>
                {metrics?.eth_dominance_pct ? `${metrics.eth_dominance_pct}%` : "—"}
              </span>
            </div>
          </div>

          {/* Tracked Assets */}
          <div className="space-y-1">
            <div className="text-[11px] font-medium uppercase tracking-wider text-muted">
              Active Cryptos
            </div>
            <div className="text-lg font-bold tracking-tight text-white tabular-nums sm:text-xl">
              {metrics?.active_cryptocurrencies
                ? metrics.active_cryptocurrencies.toLocaleString()
                : "22,500+"}
            </div>
          </div>
        </div>

        {/* Right Action: Refresh button & Sync state */}
        <div className="flex items-center justify-between border-t border-border pt-3 lg:border-t-0 lg:pt-0 gap-3">
          <div className="flex items-center gap-2 text-xs text-muted">
            <span className="inline-block h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>Local Cache Ready</span>
          </div>
          <Button
            variant="secondary"
            onClick={onRefresh}
            disabled={isRefreshing}
            className="text-xs h-8 px-3"
          >
            {isRefreshing ? (
              <span className="flex items-center gap-1.5">
                <svg
                  className="h-3.5 w-3.5 animate-spin"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
                  <path d="M12 2a10 10 0 0 1 10 10" />
                </svg>
                Syncing...
              </span>
            ) : (
              <span className="flex items-center gap-1.5">
                <svg
                  className="h-3.5 w-3.5"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2" />
                </svg>
                Sync Live
              </span>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
