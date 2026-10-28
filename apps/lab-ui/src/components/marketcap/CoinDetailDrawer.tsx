"use client";

import { useEffect } from "react";
import Link from "next/link";
import { MarketCapCoin } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { SparklineChart } from "@/components/marketcap/SparklineChart";

interface CoinDetailDrawerProps {
  coin: MarketCapCoin | null;
  onClose: () => void;
}

function formatPrice(price: number | null | undefined): string {
  if (price === null || price === undefined) return "—";
  if (price >= 1) {
    return `$${price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  if (price >= 0.01) {
    return `$${price.toFixed(4)}`;
  }
  return `$${price.toFixed(6)}`;
}

function formatCompact(val: number | null | undefined): string {
  if (val === null || val === undefined) return "—";
  if (val >= 1e12) return `$${(val / 1e12).toFixed(2)}T`;
  if (val >= 1e9) return `$${(val / 1e9).toFixed(2)}B`;
  if (val >= 1e6) return `$${(val / 1e6).toFixed(2)}M`;
  return `$${val.toLocaleString()}`;
}

function formatTokens(val: number | null | undefined, symbol: string): string {
  if (val === null || val === undefined) return "—";
  if (val >= 1e9) return `${(val / 1e9).toFixed(2)}B ${symbol}`;
  if (val >= 1e6) return `${(val / 1e6).toFixed(2)}M ${symbol}`;
  return `${val.toLocaleString()} ${symbol}`;
}

export function CoinDetailDrawer({ coin, onClose }: CoinDetailDrawerProps) {
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  if (!coin) return null;

  const change24h = coin.price_change_percentage_24h ?? 0;
  const isPos24h = change24h >= 0;

  // 24h Range calculation
  const low24 = coin.low_24h ?? coin.current_price ?? 0;
  const high24 = coin.high_24h ?? coin.current_price ?? 0;
  const current = coin.current_price ?? 0;
  const rangeSpan = high24 - low24 || 1;
  const currentPercent = Math.min(100, Math.max(0, ((current - low24) / rangeSpan) * 100));

  // Supply percentage
  const supplyPct =
    coin.circulating_supply && coin.max_supply
      ? Math.min(100, (coin.circulating_supply / coin.max_supply) * 100)
      : null;

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/60 transition-opacity duration-150"
      onClick={onClose}
      aria-modal="true"
      role="dialog"
      aria-label={`Asset details for ${coin.name}`}
    >
      <div
        className="h-full w-full max-w-xl overflow-y-auto border-l border-border-bright bg-panel-elevated p-6 shadow-overlay focus:outline-none"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header Bar */}
        <div className="flex items-start justify-between border-b border-border pb-5">
          <div className="flex items-center gap-3">
            {coin.image ? (
              <img
                src={coin.image}
                alt={coin.name}
                className="h-10 w-10 rounded-full border border-border"
              />
            ) : (
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-panel text-sm font-bold text-accent">
                {coin.symbol.slice(0, 2)}
              </div>
            )}
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold tracking-tight text-white">{coin.name}</h2>
                <span className="font-mono text-xs font-semibold uppercase text-muted">
                  {coin.symbol}
                </span>
                <span className="rounded bg-panel px-1.5 py-0.5 font-mono text-[10px] font-medium text-muted">
                  #{coin.market_cap_rank ?? "—"}
                </span>
              </div>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="text-2xl font-bold tracking-tight text-white tabular-nums">
                  {formatPrice(coin.current_price)}
                </span>
                <span
                  className={`inline-flex items-center text-xs font-semibold tabular-nums ${
                    isPos24h ? "text-emerald-400" : "text-rose-400"
                  }`}
                >
                  {isPos24h ? "+" : ""}
                  {change24h.toFixed(2)}% (24h)
                </span>
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="rounded border border-border p-1.5 text-muted hover:border-border-bright hover:text-white transition-colors duration-150"
            aria-label="Close drawer"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        {/* 7D Mini Chart Preview */}
        {coin.sparkline && coin.sparkline.length > 1 && (
          <div className="mt-5 rounded-lg border border-border bg-panel p-4">
            <div className="flex items-center justify-between text-xs text-muted mb-2">
              <span className="font-medium uppercase tracking-wider text-[10px]">
                7-Day Price Movement
              </span>
              <span className="tabular-nums">
                {coin.price_change_percentage_7d !== null && coin.price_change_percentage_7d !== undefined ? (
                  <span
                    className={
                      coin.price_change_percentage_7d >= 0 ? "text-emerald-400" : "text-rose-400"
                    }
                  >
                    {coin.price_change_percentage_7d >= 0 ? "+" : ""}
                    {coin.price_change_percentage_7d.toFixed(2)}% (7d)
                  </span>
                ) : null}
              </span>
            </div>
            <div className="flex justify-center py-2">
              <SparklineChart
                data={coin.sparkline}
                change={coin.price_change_percentage_7d}
                width={360}
                height={80}
              />
            </div>
          </div>
        )}

        {/* 24h High / Low Range */}
        <div className="mt-5 rounded-lg border border-border bg-panel p-4 space-y-2">
          <div className="flex items-center justify-between text-xs font-medium uppercase tracking-wider text-muted text-[10px]">
            <span>24h Low / High Range</span>
            <span>Position: {currentPercent.toFixed(0)}%</span>
          </div>
          <div className="relative h-2 w-full rounded-full bg-panel-elevated">
            <div
              className="absolute top-0 bottom-0 left-0 rounded-full bg-accent"
              style={{ width: `${currentPercent}%` }}
            />
          </div>
          <div className="flex items-center justify-between font-mono text-xs tabular-nums text-zinc-300">
            <span>{formatPrice(low24)}</span>
            <span className="text-muted">Current: {formatPrice(current)}</span>
            <span>{formatPrice(high24)}</span>
          </div>
        </div>

        {/* Valuation Metrics Grid */}
        <div className="mt-5 space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-muted">
            Valuation & Supply
          </h3>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="rounded border border-border bg-panel p-3">
              <div className="text-[11px] text-muted">Market Cap</div>
              <div className="mt-1 font-semibold tabular-nums text-white">
                {formatCompact(coin.market_cap)}
              </div>
            </div>
            <div className="rounded border border-border bg-panel p-3">
              <div className="text-[11px] text-muted">Fully Diluted (FDV)</div>
              <div className="mt-1 font-semibold tabular-nums text-white">
                {formatCompact(coin.fully_diluted_valuation)}
              </div>
            </div>
            <div className="rounded border border-border bg-panel p-3">
              <div className="text-[11px] text-muted">24h Trading Volume</div>
              <div className="mt-1 font-semibold tabular-nums text-white">
                {formatCompact(coin.total_volume)}
              </div>
            </div>
            <div className="rounded border border-border bg-panel p-3">
              <div className="text-[11px] text-muted">Vol / MCap Ratio</div>
              <div className="mt-1 font-semibold tabular-nums text-white">
                {coin.total_volume && coin.market_cap
                  ? (coin.total_volume / coin.market_cap).toFixed(4)
                  : "—"}
              </div>
            </div>
            <div className="col-span-2 rounded border border-border bg-panel p-3 space-y-2">
              <div className="flex justify-between text-[11px] text-muted">
                <span>Circulating Supply</span>
                <span>{supplyPct !== null ? `${supplyPct.toFixed(1)}% of Max` : "Unlimited / N/A"}</span>
              </div>
              <div className="font-semibold tabular-nums text-white">
                {formatTokens(coin.circulating_supply, coin.symbol)}
              </div>
              {supplyPct !== null && (
                <div className="h-1.5 w-full rounded-full bg-panel-elevated">
                  <div
                    className="h-1.5 rounded-full bg-emerald-500"
                    style={{ width: `${supplyPct}%` }}
                  />
                </div>
              )}
            </div>
          </div>
        </div>

        {/* All-Time Records */}
        <div className="mt-5 space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-muted">
            All-Time Records
          </h3>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="rounded border border-border bg-panel p-3">
              <div className="text-[11px] text-muted">All-Time High (ATH)</div>
              <div className="mt-1 font-semibold tabular-nums text-white">
                {formatPrice(coin.ath)}
              </div>
              <div className="mt-0.5 text-xs font-medium tabular-nums text-rose-400">
                {coin.ath_change_percentage !== null && coin.ath_change_percentage !== undefined
                  ? `${coin.ath_change_percentage.toFixed(2)}%`
                  : "—"}
              </div>
            </div>
            <div className="rounded border border-border bg-panel p-3">
              <div className="text-[11px] text-muted">All-Time Low (ATL)</div>
              <div className="mt-1 font-semibold tabular-nums text-white">
                {formatPrice(coin.atl)}
              </div>
              <div className="mt-0.5 text-xs font-medium tabular-nums text-emerald-400">
                {coin.atl_change_percentage !== null && coin.atl_change_percentage !== undefined
                  ? `+${coin.atl_change_percentage.toFixed(2)}%`
                  : "—"}
              </div>
            </div>
          </div>
        </div>

        {/* Hyperliquid Perpetual Integration */}
        {coin.hyperliquid?.is_perp_available && (
          <div className="mt-5 space-y-3">
            <div className="flex items-center gap-2">
              <span className="inline-block h-2 w-2 rounded-full bg-accent" />
              <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-100">
                Hyperliquid Perp Market
              </h3>
            </div>
            <div className="grid grid-cols-3 gap-3 text-sm">
              <div className="rounded border border-border bg-panel p-3">
                <div className="text-[11px] text-muted">Mark Price</div>
                <div className="mt-1 font-semibold tabular-nums text-white">
                  {formatPrice(coin.hyperliquid.mark_price)}
                </div>
              </div>
              <div className="rounded border border-border bg-panel p-3">
                <div className="text-[11px] text-muted">Funding (8h)</div>
                <div className="mt-1 font-semibold tabular-nums text-zinc-200">
                  {coin.hyperliquid.funding_rate !== null
                    ? `${(coin.hyperliquid.funding_rate * 100).toFixed(4)}%`
                    : "—"}
                </div>
              </div>
              <div className="rounded border border-border bg-panel p-3">
                <div className="text-[11px] text-muted">Open Interest</div>
                <div className="mt-1 font-semibold tabular-nums text-white">
                  {formatCompact(coin.hyperliquid.open_interest)}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Quant Pipeline Action CTAs */}
        <div className="mt-8 border-t border-border pt-6 space-y-3">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted">
            Launch Quant Pipelines
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <Link
              href={`/custom?symbol=${coin.symbol}&resolution=60`}
              className="w-full"
            >
              <Button variant="primary" className="w-full justify-center">
                Custom Research Pipeline
              </Button>
            </Link>
            <Link
              href={`/optimizer?symbol=${coin.symbol}&resolution=60`}
              className="w-full"
            >
              <Button variant="secondary" className="w-full justify-center">
                Optimizer Sweeps
              </Button>
            </Link>
          </div>
          <Link href="/live" className="block w-full">
            <Button variant="ghost" className="w-full justify-center border border-border text-xs">
              Live & Paper Trading Console →
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
