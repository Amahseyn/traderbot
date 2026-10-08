import type { JobRow } from "@/lib/api";
import { formatResolutionLabel } from "@/lib/format";

export type LiveTerminalSession = {
  jobId: string;
  src: string;
  dst: string;
  interval: string;
  marketSymbol: string | null;
  strategyId: string | null;
  liveOrders: boolean;
  status: string;
  logText: string;
};

export function isActiveTerminalJobStatus(status: string): boolean {
  return status === "queued" || status === "running";
}

export function liveSessionFromJob(job: JobRow): LiveTerminalSession {
  const payload = job.payload ?? {};
  const src = String(payload.src ?? "btc").trim().toLowerCase();
  const dst = String(payload.dst ?? "rls").trim().toLowerCase();
  const interval = String(payload.interval ?? "60").trim();
  const strategyId =
    typeof payload.strategy === "string" && payload.strategy.trim()
      ? payload.strategy.trim()
      : null;
  const symbolFromPayload =
    typeof payload.market_symbol === "string" ? payload.market_symbol : null;
  return {
    jobId: job.id,
    src,
    dst,
    interval,
    marketSymbol: symbolFromPayload,
    strategyId,
    liveOrders: Boolean(payload.live),
    status: job.status,
    logText: job.log_text ?? "",
  };
}

export function liveSessionPairLabel(session: LiveTerminalSession): string {
  if (session.marketSymbol) {
    return session.marketSymbol;
  }
  return `${session.src.toUpperCase()}/${session.dst.toUpperCase()}`;
}

export function liveSessionSubtitle(session: LiveTerminalSession): string {
  const pair = `${session.src.toUpperCase()}/${session.dst.toUpperCase()}`;
  const horizon = formatResolutionLabel(session.interval);
  const mode = session.liveOrders ? "Live orders" : "Paper";
  const strategy = session.strategyId ?? "strategy";
  return `${pair} · ${horizon} · ${strategy} · ${mode}`;
}

export function liveSessionSortKey(session: LiveTerminalSession): string {
  return `${isActiveTerminalJobStatus(session.status) ? "0" : "1"}-${session.jobId}`;
}
