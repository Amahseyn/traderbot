"use client";

import { formatPct } from "@/lib/format";

type PercentCellProps = {
  value: number | null | undefined;
  digits?: number;
  showArrow?: boolean;
  className?: string;
};

/**
 * Accessible percentage change cell (from financial-ui-patterns).
 * Ensures color is never the sole carrier of meaning: pairs semantic
 * colors (text-positive / text-negative) with +/- signs and ▲/▼ arrows.
 */
export function PercentCell({
  value,
  digits = 2,
  showArrow = true,
  className = "",
}: PercentCellProps) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return <span className={`tabular-nums text-muted ${className}`}>—</span>;
  }

  const isPos = value >= 0;
  const colorClass = isPos ? "text-positive" : "text-negative";
  const arrow = showArrow ? (isPos ? "▲" : "▼") : null;

  return (
    <span
      className={`inline-flex items-center gap-0.5 tabular-nums font-medium ${colorClass} ${className}`}
    >
      {arrow && <span aria-hidden="true" className="text-[10px]">{arrow}</span>}
      <span>{formatPct(value, digits, true)}</span>
    </span>
  );
}

