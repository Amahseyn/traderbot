"use client";

import { useMemo, useState } from "react";
import { Card } from "@/components/ui/Card";
import { formatMoney, formatReturnPct, returnPctClassName } from "@/lib/format";

type TradeLogEntry = {
  timestamp?: unknown;
  action?: unknown;
  price?: unknown;
  size?: unknown;
  fee?: unknown;
  cash_before?: unknown;
  cash_after?: unknown;
  position_after?: unknown;
  equity_after?: unknown;
};

type CashFlow = {
  initial_cash?: unknown;
  final_equity?: unknown;
  cash_in?: unknown;
  cash_out?: unknown;
  total_fees?: unknown;
  net_pnl?: unknown;
  return_pct?: unknown;
  buys?: unknown;
  sells?: unknown;
};

const MAX_ROWS = 500;

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatBarTime(timestamp: unknown): string {
  const seconds = asNumber(timestamp);
  if (seconds == null) return "—";
  const date = new Date(seconds * 1000);
  if (Number.isNaN(date.getTime())) return String(timestamp);
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function notional(price: number | null, size: number | null): number | null {
  if (price == null || size == null) return null;
  return price * size;
}

type SideFilter = "all" | "buy" | "sell";

export function TradeLogsTable({ metrics }: { metrics: Record<string, unknown> }) {
  const [sideFilter, setSideFilter] = useState<SideFilter>("all");

  const rawLogs = metrics.trade_logs;
  const logs: TradeLogEntry[] = Array.isArray(rawLogs) ? (rawLogs as TradeLogEntry[]) : [];
  const cashFlow: CashFlow =
    metrics.cash_flow && typeof metrics.cash_flow === "object"
      ? (metrics.cash_flow as CashFlow)
      : {};

  const filtered = useMemo(() => {
    if (sideFilter === "all") return logs;
    return logs.filter((trade) => trade.action === sideFilter);
  }, [logs, sideFilter]);

  if (logs.length === 0) return null;

  const visible = filtered.slice(0, MAX_ROWS);
  const netPnl = asNumber(cashFlow.net_pnl);
  const returnPct = asNumber(cashFlow.return_pct);
  const pnlClass =
    netPnl == null ? "text-white" : netPnl > 0 ? "text-emerald-400" : netPnl < 0 ? "text-red-400" : "text-white";

  return (
    <Card
      title={`Trade log (${logs.length} fills)`}
      description="Each row is one fill at bar close. Cash and position columns show portfolio state after the trade."
      actions={
        <div className="flex gap-1 rounded-lg border border-border bg-surface p-0.5 text-xs">
          {(["all", "buy", "sell"] as const).map((value) => (
            <button
              key={value}
              type="button"
              className={`rounded-md px-2.5 py-1 capitalize transition ${
                sideFilter === value ? "bg-accent/25 text-white" : "text-muted hover:text-white"
              }`}
              onClick={() => setSideFilter(value)}
            >
              {value === "all" ? "All" : value}
            </button>
          ))}
        </div>
      }
    >
      <dl className="mb-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
        <FlowTile label="Initial cash" value={formatMoney(asNumber(cashFlow.initial_cash) ?? undefined)} />
        <FlowTile label="Cash deployed (buys)" value={formatMoney(asNumber(cashFlow.cash_in) ?? undefined)} />
        <FlowTile label="Cash received (sells)" value={formatMoney(asNumber(cashFlow.cash_out) ?? undefined)} />
        <FlowTile label="Fees" value={formatMoney(asNumber(cashFlow.total_fees) ?? undefined)} />
        <FlowTile label="Final equity" value={formatMoney(asNumber(cashFlow.final_equity) ?? undefined)} />
        <div className="rounded-lg border border-border/80 bg-surface/60 px-3 py-2">
          <dt className="text-muted text-xs">Net PnL</dt>
          <dd className={`mt-0.5 font-medium tabular-nums ${pnlClass}`}>
            {netPnl == null ? "—" : `${netPnl > 0 ? "+" : ""}${formatMoney(netPnl)}`}
          </dd>
        </div>
        <div className="rounded-lg border border-border/80 bg-surface/60 px-3 py-2">
          <dt className="text-muted text-xs">Return</dt>
          <dd className={`mt-0.5 font-medium tabular-nums ${returnPctClassName(returnPct)}`}>
            {formatReturnPct(returnPct)}
          </dd>
        </div>
        <FlowTile label="Buys / sells" value={`${String(cashFlow.buys ?? "—")} / ${String(cashFlow.sells ?? "—")}`} />
      </dl>

      <div className="max-h-[28rem] overflow-auto rounded-lg border border-border">
        <table className="data text-xs">
          <thead className="sticky top-0 z-[1] bg-panel">
            <tr>
              <th>#</th>
              <th>Time</th>
              <th>Side</th>
              <th className="text-right">Price</th>
              <th className="text-right">Size</th>
              <th className="text-right">Notional</th>
              <th className="text-right">Fee</th>
              <th className="text-right">Cash before</th>
              <th className="text-right">Cash after</th>
              <th className="text-right">Position</th>
              <th className="text-right">Equity</th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && (
              <tr>
                <td colSpan={11} className="text-muted text-center py-6">
                  No {sideFilter === "all" ? "" : `${sideFilter} `}fills in this log.
                </td>
              </tr>
            )}
            {visible.map((trade, index) => {
              const isBuy = trade.action === "buy";
              const price = asNumber(trade.price);
              const size = asNumber(trade.size);
              const rowKey = `${String(trade.timestamp)}-${trade.action}-${index}`;
              return (
                <tr key={rowKey}>
                  <td className="tabular-nums text-muted">{index + 1}</td>
                  <td className="whitespace-nowrap">{formatBarTime(trade.timestamp)}</td>
                  <td>
                    <span className={`badge ${isBuy ? "badge-strategy" : "badge-model"}`}>
                      {isBuy ? "BUY" : "SELL"}
                    </span>
                  </td>
                  <td className="text-right tabular-nums">{formatMoney(price ?? undefined)}</td>
                  <td className="text-right tabular-nums">{size?.toFixed(6) ?? "—"}</td>
                  <td className="text-right tabular-nums">{formatMoney(notional(price, size) ?? undefined)}</td>
                  <td className="text-right tabular-nums">{formatMoney(asNumber(trade.fee) ?? undefined)}</td>
                  <td className="text-right tabular-nums">
                    {formatMoney(asNumber(trade.cash_before) ?? undefined)}
                  </td>
                  <td className="text-right tabular-nums">
                    {formatMoney(asNumber(trade.cash_after) ?? undefined)}
                  </td>
                  <td className="text-right tabular-nums">
                    {asNumber(trade.position_after)?.toFixed(6) ?? "—"}
                  </td>
                  <td className="text-right tabular-nums">
                    {formatMoney(asNumber(trade.equity_after) ?? undefined)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {filtered.length > visible.length && (
        <p className="text-muted mt-2 text-xs">
          Showing first {visible.length} of {filtered.length} fills — download the summary JSON for the full
          log.
        </p>
      )}
      {sideFilter !== "all" && filtered.length <= visible.length && filtered.length < logs.length && (
        <p className="text-muted mt-2 text-xs">
          Filtered to {filtered.length} of {logs.length} fills.
        </p>
      )}
    </Card>
  );
}

function FlowTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border/80 bg-surface/60 px-3 py-2">
      <dt className="text-muted text-xs">{label}</dt>
      <dd className="mt-0.5 font-medium text-white tabular-nums">{value}</dd>
    </div>
  );
}
