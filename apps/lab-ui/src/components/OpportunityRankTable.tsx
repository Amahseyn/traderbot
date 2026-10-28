"use client";

import { Fragment, useMemo, useState } from "react";
import type { OpportunityDiscoveryRankRow } from "@/lib/opportunityDiscoveryLog";
import { isMarketOpportunityRow } from "@/lib/opportunityDiscoveryLog";
import { formatResolutionLabel } from "@/lib/format";

type SortKey =
  | "rank"
  | "composite_score"
  | "oos_return_pct"
  | "max_drawdown_pct"
  | "trade_count"
  | "mean_quote_volume"
  | "return_1bar_pct"
  | "return_7bar_pct"
  | "realized_vol_pct"
  | "trend_score_1d"
  | "volume24h"
  | "pctChange_h24";

type OpportunityRankTableProps = {
  ranked: OpportunityDiscoveryRankRow[];
  rejected?: OpportunityDiscoveryRankRow[];
  showRejected?: boolean;
  scanKind?: string;
  coinDetails?: Record<string, unknown>;
  highlightSymbols?: string[];
};

function formatPct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) {
    return "—";
  }
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function formatNum(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) {
    return "—";
  }
  return value.toFixed(digits);
}

function formatVolume(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) {
    return "—";
  }
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(2)}M`;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`;
  }
  return value.toFixed(0);
}

function displaySymbol(row: OpportunityDiscoveryRankRow): string {
  return (row.base ?? row.symbol_key ?? "").toUpperCase();
}

/** Stable list keys (base + resolution alone collide across strategies / missing symbol). */
function rankRowReactKey(row: OpportunityDiscoveryRankRow, index: number): string {
  const parts = [
    row.symbol_key?.trim() ?? "",
    row.symbol?.trim() ?? "",
    row.strategy_id?.trim() ?? "",
    row.resolution != null ? String(row.resolution) : "",
    row.rank != null ? `rank-${row.rank}` : "",
    `i-${index}`,
  ].filter((part) => part.length > 0);
  return parts.join("|");
}

export function OpportunityRankTable({
  ranked,
  rejected = [],
  showRejected = true,
  scanKind,
  coinDetails,
  highlightSymbols,
}: OpportunityRankTableProps) {
  const coinbeaconMode = scanKind === "coinbeacon_market" || ranked.every((row) => isMarketOpportunityRow(row));
  const highlightSet = useMemo(
    () => new Set((highlightSymbols ?? []).map((symbol) => symbol.toUpperCase())),
    [highlightSymbols],
  );
  const [sortKey, setSortKey] = useState<SortKey>("rank");
  const [sortAsc, setSortAsc] = useState(true);
  const [expandedBase, setExpandedBase] = useState<string | null>(null);

  const sorted = useMemo(() => {
    const rows = [...ranked];
    rows.sort((left, right) => {
      const pick = (row: OpportunityDiscoveryRankRow) => {
        if (sortKey === "rank") {
          return row.rank ?? 0;
        }
        const value = row[sortKey];
        return typeof value === "number" ? value : -Infinity;
      };
      const delta = pick(left) - pick(right);
      return sortAsc ? delta : -delta;
    });
    return rows;
  }, [ranked, sortAsc, sortKey]);

  function header(label: string, key: SortKey) {
    const active = sortKey === key;
    return (
      <th className="text-left">
        <button
          type="button"
          className={`font-medium ${active ? "text-accent" : "text-muted hover:text-slate-200"}`}
          onClick={() => {
            if (active) {
              setSortAsc(!sortAsc);
            } else {
              setSortKey(key);
              setSortAsc(key === "rank");
            }
          }}
        >
          {label}
        </button>
      </th>
    );
  }

  if (sorted.length === 0 && rejected.length === 0) {
    return <p className="text-sm text-muted">No discovery results yet.</p>;
  }

  return (
    <div className="space-y-6">
      <div className="overflow-x-auto">
        <table className="data w-full text-sm">
          <thead>
            <tr>
              {header("Rank", "rank")}
              <th>Symbol</th>
              {!coinbeaconMode && <th>TF</th>}
              {!coinbeaconMode && <th>Strategy</th>}
              {coinbeaconMode && <th>Pair</th>}
              {coinbeaconMode && header("Trend 1d", "trend_score_1d")}
              {coinbeaconMode && header("24h %", "pctChange_h24")}
              {coinbeaconMode && header("Vol 24h", "volume24h")}
              {coinbeaconMode && <th>Screen hits</th>}
              {header("Score", "composite_score")}
              {!coinbeaconMode && <th>Regime</th>}
              {!coinbeaconMode && header("Quote vol", "mean_quote_volume")}
              {!coinbeaconMode && header("1 bar", "return_1bar_pct")}
              {!coinbeaconMode && header("7 bar", "return_7bar_pct")}
              {!coinbeaconMode && <th>30 bar</th>}
              {!coinbeaconMode && header("Realized vol", "realized_vol_pct")}
              {!coinbeaconMode && <th>Range</th>}
              {!coinbeaconMode && <th>ATR %</th>}
              {!coinbeaconMode && header("OOS return", "oos_return_pct")}
              {!coinbeaconMode && header("Max DD", "max_drawdown_pct")}
              {!coinbeaconMode && header("Trades", "trade_count")}
              {!coinbeaconMode && <th>WF stability</th>}
              {coinbeaconMode && coinDetails && <th />}
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, index) => {
              const base = displaySymbol(row);
              const rowKey = rankRowReactKey(row, index);
              const detail = coinDetails?.[base];
              const expanded = expandedBase === base;
              const highlighted = highlightSet.has(base);
              return (
                <Fragment key={rowKey}>
                  <tr className={highlighted ? "bg-accent/15 ring-1 ring-accent/30" : undefined}>
                    <td className="text-muted">{row.rank ?? "—"}</td>
                    <td className="font-medium uppercase">{base}</td>
                    {!coinbeaconMode && <td>{formatResolutionLabel(row.resolution)}</td>}
                    {!coinbeaconMode && <td>{row.strategy_id?.trim() ? row.strategy_id : "—"}</td>}
                    {coinbeaconMode && <td className="font-mono text-xs">{row.symbol ?? "—"}</td>}
                    {coinbeaconMode && <td>{formatNum(row.trend_score_1d, 0)}</td>}
                    {coinbeaconMode && <td>{formatPct(row.pctChange_h24)}</td>}
                    {coinbeaconMode && <td>{formatVolume(row.mean_quote_volume ?? row.volume24h)}</td>}
                    {coinbeaconMode && (
                      <td className="max-w-[14rem] truncate text-xs text-muted" title={(row.preset_hits ?? []).join(", ")}>
                        {(row.preset_hits ?? []).length > 0 ? row.preset_hits!.join(", ") : "—"}
                      </td>
                    )}
                    <td>{formatNum(row.composite_score, 3)}</td>
                    {!coinbeaconMode && <td className="text-muted">{row.regime_label ?? "—"}</td>}
                    {!coinbeaconMode && <td>{formatVolume(row.mean_quote_volume)}</td>}
                    {!coinbeaconMode && <td>{formatPct(row.return_1bar_pct)}</td>}
                    {!coinbeaconMode && <td>{formatPct(row.return_7bar_pct)}</td>}
                    {!coinbeaconMode && <td>{formatPct(row.return_30bar_pct)}</td>}
                    {!coinbeaconMode && <td>{formatPct(row.realized_vol_pct)}</td>}
                    {!coinbeaconMode && <td>{formatPct(row.range_pct_1bar)}</td>}
                    {!coinbeaconMode && <td>{formatPct(row.atr_pct)}</td>}
                    {!coinbeaconMode && <td>{formatPct(row.oos_return_pct)}</td>}
                    {!coinbeaconMode && <td>{formatPct(row.max_drawdown_pct)}</td>}
                    {!coinbeaconMode && <td>{row.trade_count ?? "—"}</td>}
                    {!coinbeaconMode && <td>{formatNum(row.walk_forward_stability, 2)}</td>}
                    {coinbeaconMode && coinDetails && (
                      <td>
                        {detail ? (
                          <button
                            type="button"
                            className="text-xs text-accent hover:underline"
                            onClick={() => setExpandedBase(expanded ? null : base)}
                          >
                            {expanded ? "Hide" : "Funding"}
                          </button>
                        ) : (
                          "—"
                        )}
                      </td>
                    )}
                  </tr>
                  {coinbeaconMode && expanded && Boolean(detail) && (
                    <tr key={`${rowKey}-detail`}>
                      <td colSpan={9} className="bg-surface/40 p-3">
                        <pre className="max-h-48 overflow-auto text-xs whitespace-pre-wrap font-mono text-muted">
                          {JSON.stringify(detail, null, 2)}
                        </pre>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      {showRejected && rejected.length > 0 && (
        <details className="rounded-lg border border-border/80 bg-surface/40 px-3 py-2 text-sm">
          <summary className="cursor-pointer font-medium text-muted">
            Rejected candidates ({rejected.length})
          </summary>
          <ul className="mt-2 space-y-1 text-xs text-muted">
            {rejected.slice(0, 40).map((row, index) => (
              <li key={`rej-${rankRowReactKey(row, index)}`}>
                <span className="uppercase">{displaySymbol(row)}</span>
                {!coinbeaconMode && ` · ${formatResolutionLabel(row.resolution)}`}
                {row.strategy_id?.trim() ? ` · ${row.strategy_id}` : ""}: {row.rejection_reason ?? "ineligible"}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
