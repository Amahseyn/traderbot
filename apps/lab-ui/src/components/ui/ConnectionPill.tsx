"use client";

import { formatRelativeTime } from "@/lib/format";

export type ConnectionStatus = "connecting" | "live" | "stale" | "disconnected";

const STATUS_CONFIG: Record<
  ConnectionStatus,
  { dotClass: string; label: string; badgeClass: string }
> = {
  connecting: {
    dotClass: "bg-warning animate-pulse",
    label: "Connecting",
    badgeClass: "border-warning/30 bg-warning/10 text-warning",
  },
  live: {
    dotClass: "bg-positive",
    label: "Live",
    badgeClass: "border-positive/30 bg-positive/10 text-positive",
  },
  stale: {
    dotClass: "bg-warning",
    label: "Stale",
    badgeClass: "border-warning/30 bg-warning/10 text-warning",
  },
  disconnected: {
    dotClass: "bg-negative",
    label: "Disconnected",
    badgeClass: "border-negative/30 bg-negative/10 text-negative",
  },
};

type ConnectionPillProps = {
  status: ConnectionStatus;
  lastUpdateIso?: string;
  className?: string;
};

/**
 * WebSocket streaming connection state indicator (from financial-ui-patterns).
 * Conveys connectivity health with dual cues (color + explicit text label).
 */
export function ConnectionPill({
  status,
  lastUpdateIso,
  className = "",
}: ConnectionPillProps) {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.disconnected;

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[11px] font-medium tracking-wide ${config.badgeClass} ${className}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${config.dotClass}`} aria-hidden />
      <span>{config.label}</span>
      {lastUpdateIso && status !== "live" && (
        <span className="text-muted tabular-nums">· {formatRelativeTime(lastUpdateIso)}</span>
      )}
    </span>
  );
}

