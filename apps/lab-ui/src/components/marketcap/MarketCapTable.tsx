"use client";

import Link from "next/link";
import { MarketCapCoin } from "@/lib/api";
import { SparklineChart } from "@/components/marketcap/SparklineChart";

interface MarketCapTableProps {
  coins: MarketCapCoin[];
  selectedCoin: MarketCapCoin | null;
  onSelectCoin: (coin: MarketCapCoin) => void;
  sortBy: string;
  sortDir: string;
  onSort: (column: string) => void;
  isLoading: boolean;
}

function formatPrice(price: number | null | undefined): string {
  if (price === null || price === undefined) return "—";
  if (price >= 1000) {
    return `$${price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  if (price >= 1) {
    return `$${price.toFixed(2)}`;
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

function formatSupply(val: number | null | undefined, symbol: string): string {
  if (val === null || val === undefined) return "—";
  if (val >= 1e9) return `${(val / 1e9).toFixed(2)}B ${symbol}`;
  if (val >= 1e6) return `${(val / 1e6).toFixed(2)}M ${symbol}`;
  return `${val.toLocaleString()} ${symbol}`;
}

function PercentChangeCell({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) {
    return <span className="text-muted">—</span>;
  }
  const isPos = value >= 0;
  return (
    <span
      className={`inline-flex items-center gap-0.5 font-semibold tabular-nums text-xs ${
        isPos ? "text-emerald-400" : "text-rose-400"
      }`}
    >
      <span aria-hidden="true">{isPos ? "▲" : "▼"}</span>
      <span>
        {Math.abs(value).toFixed(2)}%
      </span>
    </span>
  );
}

export function MarketCapTable({
  coins,
  selectedCoin,
  onSelectCoin,
  sortBy,
  sortDir,
  onSort,
  isLoading,
}: MarketCapTableProps) {
  function renderSortHeader(label: string, field: string, align: "left" | "right" = "right") {
    const isCurrent = sortBy === field;
    const ariaSort = isCurrent
      ? sortDir === "asc"
        ? "ascending"
        : "descending"
      : "none";

    return (
      <th
        scope="col"
        aria-sort={ariaSort}
        onClick={() => onSort(field)}
        className={`cursor-pointer select-none py-3 px-3 text-[11px] font-semibold uppercase tracking-wider text-muted hover:text-white transition-colors duration-150 ${
          align === "right" ? "text-right" : "text-left"
        }`}
      >
        <div className={`inline-flex items-center gap-1 ${align === "right" ? "justify-end" : "justify-start"}`}>
          <span>{label}</span>
          <span className="text-[10px] text-border-bright">
            {isCurrent ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
          </span>
        </div>
      </th>
    );
  }

  if (isLoading && coins.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-sm text-muted">
        <svg
          className="h-6 w-6 animate-spin text-accent mb-3"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
          <path d="M12 2a10 10 0 0 1 10 10" />
        </svg>
        <span>Loading market cap rankings...</span>
      </div>
    );
  }

  if (coins.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-panel p-12 text-center text-sm text-muted">
        No cryptocurrencies match your query. Try adjusting filters or search term.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-panel">
      <table className="w-full border-collapse text-left data text-sm">
        <thead className="bg-panel-elevated border-b border-border">
          <tr>
            {renderSortHeader("#", "market_cap_rank", "left")}
            {renderSortHeader("Name", "name", "left")}
            {renderSortHeader("Price", "current_price", "right")}
            {renderSortHeader("1h %", "price_change_percentage_1h", "right")}
            {renderSortHeader("24h %", "price_change_percentage_24h", "right")}
            {renderSortHeader("7d %", "price_change_percentage_7d", "right")}
            {renderSortHeader("24h Volume", "total_volume", "right")}
            {renderSortHeader("Market Cap", "market_cap", "right")}
            <th scope="col" className="py-3 px-3 text-right text-[11px] font-semibold uppercase tracking-wider text-muted hidden md:table-cell">
              Circulating Supply
            </th>
            <th scope="col" className="py-3 px-3 text-center text-[11px] font-semibold uppercase tracking-wider text-muted hidden lg:table-cell">
              Last 7 Days
            </th>
            <th scope="col" className="py-3 px-3 text-right text-[11px] font-semibold uppercase tracking-wider text-muted">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {coins.map((coin) => {
            const isSelected = selectedCoin?.id === coin.id;
            const supplyPct =
              coin.circulating_supply && coin.max_supply
                ? Math.min(100, (coin.circulating_supply / coin.max_supply) * 100)
                : null;

            return (
              <tr
                key={coin.id}
                onClick={() => onSelectCoin(coin)}
                className={`cursor-pointer transition-colors duration-150 hover:bg-panel-elevated/70 ${
                  isSelected ? "bg-panel-elevated ring-1 ring-inset ring-accent/30" : ""
                }`}
              >
                {/* Rank */}
                <td className="py-3.5 px-3 font-mono text-xs text-muted tabular-nums whitespace-nowrap">
                  {coin.market_cap_rank ?? "—"}
                </td>

                {/* Coin Info */}
                <td className="py-3.5 px-3 whitespace-nowrap">
                  <div className="flex items-center gap-2.5">
                    {coin.image ? (
                      <img
                        src={coin.image}
                        alt=""
                        className="h-6 w-6 rounded-full border border-border bg-panel shrink-0"
                        loading="lazy"
                      />
                    ) : (
                      <div className="flex h-6 w-6 items-center justify-center rounded-full bg-panel-elevated text-[10px] font-bold text-accent shrink-0">
                        {coin.symbol.slice(0, 2)}
                      </div>
                    )}
                    <div className="flex items-baseline gap-1.5 min-w-0">
                      <span className="font-semibold text-white truncate max-w-[120px] sm:max-w-[160px]">
                        {coin.name}
                      </span>
                      <span className="font-mono text-[11px] text-muted uppercase">
                        {coin.symbol}
                      </span>
                      {coin.hyperliquid?.is_perp_available && (
                        <span className="hidden sm:inline-block rounded bg-accent/15 px-1 py-0.2 font-mono text-[9px] font-semibold uppercase tracking-tight text-accent">
                          HL Perp
                        </span>
                      )}
                    </div>
                  </div>
                </td>

                {/* Price */}
                <td className="py-3.5 px-3 text-right font-mono font-medium text-white tabular-nums whitespace-nowrap">
                  {formatPrice(coin.current_price)}
                </td>

                {/* 1h % */}
                <td className="py-3.5 px-3 text-right whitespace-nowrap">
                  <PercentChangeCell value={coin.price_change_percentage_1h} />
                </td>

                {/* 24h % */}
                <td className="py-3.5 px-3 text-right whitespace-nowrap">
                  <PercentChangeCell value={coin.price_change_percentage_24h} />
                </td>

                {/* 7d % */}
                <td className="py-3.5 px-3 text-right whitespace-nowrap">
                  <PercentChangeCell value={coin.price_change_percentage_7d} />
                </td>

                {/* 24h Volume */}
                <td className="py-3.5 px-3 text-right font-mono text-xs tabular-nums text-zinc-300 whitespace-nowrap">
                  {formatCompact(coin.total_volume)}
                </td>

                {/* Market Cap */}
                <td className="py-3.5 px-3 text-right font-mono text-xs font-semibold tabular-nums text-white whitespace-nowrap">
                  {formatCompact(coin.market_cap)}
                </td>

                {/* Circulating Supply */}
                <td className="py-3.5 px-3 text-right font-mono text-xs tabular-nums text-zinc-300 whitespace-nowrap hidden md:table-cell">
                  <div>{formatSupply(coin.circulating_supply, coin.symbol)}</div>
                  {supplyPct !== null && (
                    <div className="mt-1 ml-auto h-1 w-20 rounded-full bg-panel-elevated">
                      <div
                        className="h-1 rounded-full bg-emerald-500"
                        style={{ width: `${supplyPct}%` }}
                      />
                    </div>
                  )}
                </td>

                {/* Last 7 Days Sparkline */}
                <td className="py-3.5 px-3 text-center whitespace-nowrap hidden lg:table-cell">
                  <div className="flex justify-center">
                    <SparklineChart
                      data={coin.sparkline}
                      change={coin.price_change_percentage_7d}
                      width={110}
                      height={32}
                    />
                  </div>
                </td>

                {/* Actions */}
                <td className="py-3.5 px-3 text-right whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                  <div className="flex items-center justify-end gap-1.5">
                    <button
                      type="button"
                      onClick={() => onSelectCoin(coin)}
                      className="rounded border border-border bg-panel px-2 py-1 text-xs font-medium text-zinc-300 hover:border-border-bright hover:text-white transition-colors duration-150"
                    >
                      Details
                    </button>
                    <Link
                      href={`/custom?symbol=${coin.symbol}&resolution=60`}
                      className="rounded border border-border bg-panel px-2 py-1 text-xs font-medium text-accent hover:border-border-bright hover:bg-accent/10 transition-colors duration-150"
                      title="Launch backtest in Custom Research"
                    >
                      Lab
                    </Link>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
