"use client";

import { useEffect, useRef, useState } from "react";
import { formatCryptoPrice } from "@/lib/format";

type PriceCellProps = {
  value: number | null | undefined;
  format?: (n: number) => string;
  enableFlash?: boolean;
  prefix?: string;
  className?: string;
};

/**
 * Direction-aware streaming price cell (from financial-ui-patterns).
 * Applies CSS-only flash tint (up/green, down/red) on price changes
 * without JS render loop overhead, maintaining strict tabular-nums.
 */
export function PriceCell({
  value,
  format,
  enableFlash = true,
  prefix = "$",
  className = "",
}: PriceCellProps) {
  const prevRef = useRef<number | null | undefined>(value);
  const [flash, setFlash] = useState<"up" | "down" | null>(null);

  useEffect(() => {
    if (!enableFlash || value === null || value === undefined) {
      prevRef.current = value;
      return;
    }
    const prev = prevRef.current;
    if (prev !== null && prev !== undefined && value !== prev) {
      setFlash(value > prev ? "up" : "down");
      const timer = setTimeout(() => setFlash(null), 350);
      prevRef.current = value;
      return () => clearTimeout(timer);
    }
    prevRef.current = value;
  }, [value, enableFlash]);

  if (value === null || value === undefined || !Number.isFinite(value)) {
    return <span className={`tabular-nums text-muted ${className}`}>—</span>;
  }

  const formatted = format ? format(value) : formatCryptoPrice(value, prefix);

  return (
    <span
      data-flash={flash ?? undefined}
      className={`tabular-nums rounded-sm px-1 font-medium transition-colors duration-300 ${className}`}
    >
      {formatted}
    </span>
  );
}

