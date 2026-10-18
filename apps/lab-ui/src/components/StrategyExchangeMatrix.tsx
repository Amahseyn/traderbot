"use client";

import Link from "next/link";
import type { StrategyExchangeCatalog } from "@/lib/api";

const STRATEGY_LABELS: Record<string, string> = {
  pair_trading: "Pair trading",
  spot_grid: "Spot / perp grid",
  funding_carry: "Funding carry",
  perp_market_making: "Perp market making",
};

const EXCHANGE_LABELS: Record<string, string> = {
  hyperliquid: "Hyperliquid",
  nobitex: "Nobitex",
};

type StrategyExchangeMatrixProps = {
  catalog: StrategyExchangeCatalog;
};

export function StrategyExchangeMatrix({ catalog }: StrategyExchangeMatrixProps) {
  const exchanges = catalog.exchanges;
  const rows = Object.entries(catalog.strategies).sort(([left], [right]) =>
    left.localeCompare(right),
  );

  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <table className="data text-sm">
        <thead>
          <tr>
            <th>Strategy</th>
            {exchanges.map((exchange) => (
              <th key={exchange} className="text-center">
                {EXCHANGE_LABELS[exchange] ?? exchange}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(([strategyId, supported]) => (
            <tr key={strategyId}>
              <td>{STRATEGY_LABELS[strategyId] ?? strategyId}</td>
              {exchanges.map((exchange) => {
                const on = supported.includes(exchange);
                return (
                  <td key={exchange} className="text-center text-muted">
                    {on ? (
                      <span className="text-emerald-400" title="Supported">Yes</span>
                    ) : (
                      <span title="Not supported">—</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-border px-3 py-2 text-xs text-muted">
        Perp market making is evaluated via CLI/scripts; UI backtest coming later. Rule strategies (SMA, RSI, …)
        run on any exported OHLC via{" "}
        <Link href="/custom" className="text-accent hover:underline">Custom research</Link>.
      </p>
    </div>
  );
}
