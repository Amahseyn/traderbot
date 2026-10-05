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

/** Nobitex resolution token (`60`, `D`, `2D`) → minutes per candle. */
export function minutesFromResolution(resolution: string | null | undefined): number | null {
  if (!resolution) return null;
  const token = resolution.trim().toUpperCase();
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

export function parseReturnPct(metrics: Record<string, unknown> | undefined): number | null {
  if (!metrics) return null;
  const raw = metrics.return_pct;
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

export function returnPctClassName(value: number | null): string {
  if (value == null) return "text-muted";
  if (value > 0) return "text-emerald-400";
  if (value < 0) return "text-red-400";
  return "text-muted";
}

export function formatResolutionLabel(resolution: string | null | undefined): string {
  if (!resolution?.trim()) return "—";
  const minutes = minutesFromResolution(resolution);
  if (minutes == null) return resolution;
  if (minutes >= DAY_MINUTES && minutes % DAY_MINUTES === 0) {
    const days = minutes / DAY_MINUTES;
    return days === 1 ? "1 day" : `${days} day candles`;
  }
  return `${formatDurationMinutes(minutes)} candles`;
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
