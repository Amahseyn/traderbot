export function formatBytes(sizeBytes: number): string {
  if (sizeBytes < 1024) {
    return `${sizeBytes} B`;
  }
  if (sizeBytes < 1024 * 1024) {
    return `${(sizeBytes / 1024).toFixed(1)} KB`;
  }
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
}

const DAY_MINUTES = 24 * 60;

/** Nobitex resolution token (`60`, `D`, `2D`, or compound like `60_last24h`) → minutes per candle. */
export function minutesFromResolution(resolution: string | null | undefined): number | null {
  if (!resolution) return null;
  const token = resolution.trim().toUpperCase().split("_")[0];
  if (/^\d+$/.test(token)) {
    const minutes = Number(token);
    return minutes >= 1 ? minutes : null;
  }
  const days = /^(\d*)D$/.exec(token);
  if (!days) return null;
  const count = days[1] ? Number(days[1]) : 1;
  return count >= 1 ? count * DAY_MINUTES : null;
}

/** Clock length for a minute count: `90` → `1 hour 30 minutes`. */
export function formatDurationMinutes(totalMinutes: number): string {
  const minutes = Math.max(0, Math.round(totalMinutes));
  if (minutes === 0) return "0 minutes";
  const days = Math.floor(minutes / DAY_MINUTES);
  const hours = Math.floor((minutes % DAY_MINUTES) / 60);
  const remainder = minutes % 60;
  const parts: string[] = [];
  if (days) parts.push(days === 1 ? "1 day" : `${days} days`);
  if (hours) parts.push(hours === 1 ? "1 hour" : `${hours} hours`);
  if (remainder) parts.push(remainder === 1 ? "1 minute" : `${remainder} minutes`);
  return parts.join(" ");
}

export function formatUtcTimestamp(iso: string): string {
  const parsed = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  if (Number.isNaN(parsed.getTime())) {
    return iso;
  }
  return parsed.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

/**
 * Relative time label for an ISO timestamp: "just now", "5 minutes ago",
 * "3 hours ago", "2 days ago", etc. Falls back to the absolute timestamp
 * for anything older than 30 days.
 */
export function formatRelativeTime(iso: string): string {
  const parsed = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  if (Number.isNaN(parsed.getTime())) {
    return iso;
  }
  const now = Date.now();
  const diffMs = now - parsed.getTime();
  if (diffMs < 0) {
    // Future timestamp — just show the absolute time.
    return formatUtcTimestamp(iso);
  }
  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 45) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 1) return "just now";
  if (minutes < 60) return minutes === 1 ? "1 minute ago" : `${minutes} minutes ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return hours === 1 ? "1 hour ago" : `${hours} hours ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return days === 1 ? "1 day ago" : `${days} days ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return months === 1 ? "1 month ago" : `${months} months ago`;
  const years = Math.floor(days / 365);
  return years === 1 ? "1 year ago" : `${years} years ago`;
}

export function parseReturnPct(metrics: Record<string, unknown> | undefined): number | null {
  if (!metrics) return null;
  const raw =
    metrics.return_pct ??
    (metrics.cash_flow as Record<string, unknown> | undefined)?.return_pct;
  if (typeof raw === "number" && Number.isFinite(raw)) return raw;
  if (typeof raw === "string" && raw.trim()) {
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

export function formatReturnPct(value: number | null, digits = 2): string {
  if (value == null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

export function formatWinRate(value: number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${value.toFixed(digits)}%`;
}

export function returnPctClassName(value: number | null): string {
  if (value == null) return "text-muted";
  if (value > 0) return "text-positive";
  if (value < 0) return "text-negative";
  return "text-muted";
}

/**
 * Magnitude-aware crypto price formatting (from financial-ui-patterns).
 * Prevents naive toFixed(2) truncating sub-dollar / altcoin assets, while
 * properly grouping thousands on major assets (BTC, ETH).
 */
export function formatCryptoPrice(price: number | null | undefined, currencyPrefix = "$"): string {
  if (price === null || price === undefined || !Number.isFinite(price)) return "—";
  if (price >= 1000) {
    return `${currencyPrefix}${price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  if (price >= 1) {
    return `${currencyPrefix}${price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;
  }
  if (price >= 0.01) {
    return `${currencyPrefix}${price.toFixed(4)}`;
  }
  if (price >= 0.0001) {
    return `${currencyPrefix}${price.toFixed(6)}`;
  }
  if (price >= 0.00000001) {
    return `${currencyPrefix}${price.toFixed(8)}`;
  }
  return `${currencyPrefix}${price.toExponential(2)}`;
}

/**
 * Compact unit formatting for market cap, volume, and total liquidity.
 */
export function formatCompact(val: number | null | undefined, prefix = "$"): string {
  if (val === null || val === undefined || !Number.isFinite(val)) return "—";
  if (val >= 1e12) return `${prefix}${(val / 1e12).toFixed(2)}T`;
  if (val >= 1e9) return `${prefix}${(val / 1e9).toFixed(2)}B`;
  if (val >= 1e6) return `${prefix}${(val / 1e6).toFixed(2)}M`;
  if (val >= 1e3) return `${prefix}${(val / 1e3).toFixed(1)}K`;
  return `${prefix}${val.toLocaleString("en-US")}`;
}

/**
 * Basis points formatting for spreads, fee rates, and funding carry.
 */
export function formatBps(bps: number | null | undefined): string {
  if (bps === null || bps === undefined || !Number.isFinite(bps)) return "—";
  if (Math.abs(bps) < 100) return `${bps.toFixed(1)} bps`;
  return `${(bps / 100).toFixed(2)}%`;
}

/**
 * Standard percentage formatting with explicit sign.
 */
export function formatPct(value: number | null | undefined, digits = 2, showPlus = true): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const sign = value > 0 && showPlus ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

export function formatResolutionLabel(resolution: string | null | undefined): string {
  if (!resolution?.trim()) return "—";
  const trimmed = resolution.trim();
  const minutes = minutesFromResolution(trimmed);
  if (minutes == null) return trimmed;
  let baseLabel: string;
  if (minutes >= DAY_MINUTES && minutes % DAY_MINUTES === 0) {
    const days = minutes / DAY_MINUTES;
    baseLabel = days === 1 ? "1 day" : `${days} day candles`;
  } else {
    baseLabel = `${formatDurationMinutes(minutes)} candles`;
  }
  const underscoreIndex = trimmed.indexOf("_");
  if (underscoreIndex >= 0) {
    const suffix = trimmed.slice(underscoreIndex + 1);
    return `${baseLabel} (${suffix})`;
  }
  return baseLabel;
}

export function formatMoney(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

/** Convert catalog date-only bounds to `datetime-local` defaults (UTC midnight). */
export function utcDateToDatetimeLocal(dateOnly: string | null | undefined): string {
  if (!dateOnly?.trim()) return "";
  const day = dateOnly.trim().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return "";
  return `${day}T00:00`;
}

/** Send Lab API run window fields (`run_start_utc` / `run_end_utc`). */
export function datetimeLocalToUtcIso(localValue: string): string {
  const trimmed = localValue.trim();
  if (!trimmed) return "";
  const parsed = new Date(trimmed);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toISOString();
}

/** Format minutes per bar for run-window hints. */
export function formatBarIntervalHint(minutes: number | null): string {
  if (minutes == null) return "each file’s candle size";
  return `${formatDurationMinutes(minutes)} candles`;
}

/** Normalize absolute or repo-relative paths for the artifact API. */
export function normalizeArtifactPath(filePath: string): string {
  const normalized = filePath.replace(/\\/g, "/");
  for (const root of ["/data/", "/results/", "/solutions/"]) {
    const index = normalized.indexOf(root);
    if (index >= 0) {
      return normalized.slice(index + 1);
    }
  }
  return normalized.replace(/^\//, "");
}
