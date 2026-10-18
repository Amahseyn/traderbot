export type TradeMarker = {
  timestamp: number;
  action: "buy" | "sell";
  price: number;
  mode?: string;
  strategy_id?: string;
};

export type PaperPortfolioSnapshot = {
  quote_cash: number;
  quote_currency: string;
  base_amount: number;
  equity: number;
  mark_price: number;
  base_value?: number;
  mark_kind?: string;
};

export type EquityPoint = {
  timestamp: number;
  equity: number;
  mark_price: number | null;
  poll: number | null;
  source: "tick" | "signal" | "once" | "paper_wallet";
  status?: string;
};

export type LiveSessionMetrics = {
  initialCash: number | null;
  currentEquity: number | null;
  sessionReturnPct: number | null;
  sessionPnl: number | null;
  peakEquity: number | null;
  drawdownPct: number | null;
  tradeCount: number;
  buyCount: number;
  sellCount: number;
  /** Completed buy→sell pairs in chronological order. */
  roundTripCount: number;
  /** Buy signals not yet closed by a sell (long-only paper). */
  openBuyLegs: number;
  firstActivityUnix: number | null;
  baseExposurePct: number | null;
};

export type LiveTickStats = {
  evaluated: number;
  noNewBar: number;
  blocked: number;
  signals: number;
};

export type LiveTuneSweepEvent = {
  strategy?: string;
  symbol?: string;
  interval?: string;
  status?: string;
  return_pct?: number;
  holdout_return_pct?: number;
  trades?: number;
  combinations?: number;
  best_params?: Record<string, unknown>;
};

export type LiveLogSummary = {
  markers: TradeMarker[];
  paperWallet: PaperPortfolioSnapshot | null;
  paperInitialCash: number | null;
  strategyIds: string[];
  terminalBanner: Record<string, unknown> | null;
  liveTuneEvents: LiveTuneSweepEvent[];
  liveTuneStarted: boolean;
  liveTuneCompleted: boolean;
  phases: string[];
};

function parseJsonLine(line: string): Record<string, unknown> | null {
  const trimmed = line.trim();
  if (!trimmed.startsWith("{")) {
    return null;
  }
  try {
    const row = JSON.parse(trimmed) as Record<string, unknown>;
    return row && typeof row === "object" ? row : null;
  } catch {
    return null;
  }
}

export function summarizeLiveJobLog(logText: string): LiveLogSummary {
  const markers: TradeMarker[] = [];
  let paperWallet: PaperPortfolioSnapshot | null = null;
  let paperInitialCash: number | null = null;
  const strategyIds: string[] = [];
  const seenStrategy = new Set<string>();
  let terminalBanner: Record<string, unknown> | null = null;
  const liveTuneEvents: LiveTuneSweepEvent[] = [];
  let liveTuneStarted = false;
  let liveTuneCompleted = false;
  let hasSignalActivity = false;

  for (const line of logText.split("\n")) {
    const row = parseJsonLine(line);
    if (!row) {
      continue;
    }
    const event = row.event;
    const strategyRaw = row.strategy_id ?? row.strategy;
    if (typeof strategyRaw === "string" && strategyRaw.trim()) {
      const key = strategyRaw.trim();
      if (!seenStrategy.has(key)) {
        seenStrategy.add(key);
        strategyIds.push(key);
      }
    }

    if (event === "paper_wallet" && typeof row.initial_cash === "number") {
      paperInitialCash = row.initial_cash;
    }
    if (row.portfolio && typeof row.portfolio === "object") {
      paperWallet = row.portfolio as PaperPortfolioSnapshot;
    }
    if (event === "signal" || event === "once" || event === "tick") {
      hasSignalActivity = true;
    }
    if (event === "signal" || event === "once") {
      const action = row.action;
      if (action !== "buy" && action !== "sell") {
        continue;
      }
      const timestamp = Number(row.timestamp ?? row.bar_timestamp);
      const price = Number(row.close);
      if (!Number.isFinite(timestamp) || !Number.isFinite(price)) {
        continue;
      }
      markers.push({
        timestamp,
        action,
        price,
        mode: typeof row.mode === "string" ? row.mode : undefined,
        strategy_id: typeof strategyRaw === "string" ? strategyRaw : undefined,
      });
    }

    const terminal = row.terminal;
    if (terminal === "live" || terminal === "once") {
      terminalBanner = row;
    }
    if (event === "live_tune_start") {
      liveTuneStarted = true;
    }
    if (event === "live_tune_complete") {
      liveTuneCompleted = true;
    }
    if (event === "live_tune_sweep") {
      liveTuneEvents.push({
        strategy: typeof row.strategy === "string" ? row.strategy : undefined,
        symbol: typeof row.symbol === "string" ? row.symbol : undefined,
        interval: typeof row.interval === "string" ? row.interval : undefined,
        status: typeof row.status === "string" ? row.status : undefined,
        return_pct: typeof row.return_pct === "number" ? row.return_pct : undefined,
        holdout_return_pct:
          typeof row.holdout_return_pct === "number" ? row.holdout_return_pct : undefined,
        trades: typeof row.trades === "number" ? row.trades : undefined,
        combinations: typeof row.combinations === "number" ? row.combinations : undefined,
        best_params:
          row.best_params && typeof row.best_params === "object"
            ? (row.best_params as Record<string, unknown>)
            : undefined,
      });
    }
  }

  const phases: string[] = [];
  if (liveTuneStarted) {
    phases.push("optimize");
  }
  if (liveTuneEvents.length > 0) {
    phases.push("optimize_result");
  }
  if (liveTuneCompleted) {
    phases.push("optimize_done");
  }
  if (terminalBanner && typeof terminalBanner.terminal === "string") {
    phases.push(`terminal_${terminalBanner.terminal}`);
  }
  if (markers.length > 0 || hasSignalActivity) {
    phases.push("signals");
  }

  return {
    markers,
    paperWallet,
    paperInitialCash,
    strategyIds,
    terminalBanner,
    liveTuneEvents,
    liveTuneStarted,
    liveTuneCompleted,
    phases,
  };
}

function portfolioFromRow(row: Record<string, unknown>): PaperPortfolioSnapshot | null {
  if (!row.portfolio || typeof row.portfolio !== "object") {
    return null;
  }
  const portfolio = row.portfolio as Record<string, unknown>;
  const equity = Number(portfolio.equity);
  if (!Number.isFinite(equity)) {
    return null;
  }
  return portfolio as PaperPortfolioSnapshot;
}

function timestampFromRow(row: Record<string, unknown>, pollFallback: number): number {
  const barTs = row.bar_timestamp;
  if (barTs != null && Number.isFinite(Number(barTs)) && Number(barTs) > 1_000_000) {
    return Number(barTs);
  }
  const ts = row.timestamp;
  if (ts != null && Number.isFinite(Number(ts)) && Number(ts) > 1_000_000) {
    return Number(ts);
  }
  return pollFallback;
}

/** Ordered equity snapshots from terminal JSON log (ticks, fills, opening wallet). */
export function parseLiveEquitySeries(logText: string): EquityPoint[] {
  const series: EquityPoint[] = [];
  let pollSequence = 0;
  let lastTimestamp = 0;

  for (const line of logText.split("\n")) {
    const row = parseJsonLine(line);
    if (!row) {
      continue;
    }
    const event = row.event;
    if (event === "tick" && typeof row.poll === "number") {
      pollSequence = row.poll;
    }

    if (event === "paper_wallet" && typeof row.initial_cash === "number") {
      const ts = lastTimestamp > 0 ? lastTimestamp : pollSequence;
      series.push({
        timestamp: ts,
        equity: row.initial_cash,
        mark_price: null,
        poll: null,
        source: "paper_wallet",
      });
      continue;
    }

    const portfolio = portfolioFromRow(row);
    if (!portfolio) {
      continue;
    }

    const poll = typeof row.poll === "number" ? row.poll : null;
    const ts = timestampFromRow(row, pollSequence > 0 ? pollSequence : series.length);
    if (ts > 1_000_000) {
      lastTimestamp = ts;
    }
    const source: EquityPoint["source"] =
      event === "signal" ? "signal" : event === "once" ? "once" : "tick";
    series.push({
      timestamp: ts > 1_000_000 ? ts : lastTimestamp > 0 ? lastTimestamp : series.length,
      equity: portfolio.equity,
      mark_price: Number.isFinite(Number(portfolio.mark_price)) ? Number(portfolio.mark_price) : null,
      poll,
      source,
      status: typeof row.status === "string" ? row.status : undefined,
    });
  }

  return series;
}

export function parseLiveTickStats(logText: string): LiveTickStats {
  const stats: LiveTickStats = { evaluated: 0, noNewBar: 0, blocked: 0, signals: 0 };
  for (const line of logText.split("\n")) {
    const row = parseJsonLine(line);
    if (!row) {
      continue;
    }
    if (row.event === "signal" || row.event === "once") {
      stats.signals += 1;
    }
    if (row.event !== "tick") {
      continue;
    }
    const status = row.status;
    if (status === "evaluated") {
      stats.evaluated += 1;
    } else if (status === "no_new_bar") {
      stats.noNewBar += 1;
    } else if (status === "blocked") {
      stats.blocked += 1;
    }
  }
  return stats;
}

export function countLiveFillStats(markers: TradeMarker[]): {
  buyCount: number;
  sellCount: number;
  roundTripCount: number;
  openBuyLegs: number;
} {
  const sorted = [...markers].sort((left, right) => left.timestamp - right.timestamp);
  let buyCount = 0;
  let sellCount = 0;
  let roundTripCount = 0;
  let openBuyLegs = 0;
  for (const marker of sorted) {
    if (marker.action === "buy") {
      buyCount += 1;
      openBuyLegs += 1;
      continue;
    }
    sellCount += 1;
    if (openBuyLegs > 0) {
      openBuyLegs -= 1;
      roundTripCount += 1;
    }
  }
  return { buyCount, sellCount, roundTripCount, openBuyLegs };
}

export function computeLiveSessionMetrics(
  summary: LiveLogSummary,
  equitySeries: EquityPoint[],
): LiveSessionMetrics {
  const initialCash =
    summary.paperInitialCash ??
    equitySeries.find((point) => point.source === "paper_wallet")?.equity ??
    null;
  const lastPoint = equitySeries.length > 0 ? equitySeries[equitySeries.length - 1] : null;
  const currentEquity = summary.paperWallet?.equity ?? lastPoint?.equity ?? initialCash;

  let peakEquity: number | null = null;
  let drawdownPct: number | null = null;
  if (equitySeries.length > 0) {
    let peak = equitySeries[0].equity;
    let maxDd = 0;
    for (const point of equitySeries) {
      peak = Math.max(peak, point.equity);
      if (peak > 0) {
        const dd = ((peak - point.equity) / peak) * 100;
        maxDd = Math.max(maxDd, dd);
      }
    }
    peakEquity = peak;
    drawdownPct = maxDd;
  }

  let sessionReturnPct: number | null = null;
  let sessionPnl: number | null = null;
  if (initialCash != null && initialCash > 0 && currentEquity != null) {
    sessionPnl = currentEquity - initialCash;
    sessionReturnPct = (sessionPnl / initialCash) * 100;
  }

  const fillStats = countLiveFillStats(summary.markers);
  const { buyCount, sellCount, roundTripCount, openBuyLegs } = fillStats;

  const firstActivityUnix =
    equitySeries.find((point) => point.timestamp > 1_000_000_000)?.timestamp ??
    summary.markers[0]?.timestamp ??
    null;

  let baseExposurePct: number | null = null;
  const wallet = summary.paperWallet;
  if (wallet && wallet.equity > 0) {
    const baseValue =
      wallet.base_value != null && Number.isFinite(wallet.base_value)
        ? wallet.base_value
        : wallet.base_amount * wallet.mark_price;
    if (Number.isFinite(baseValue)) {
      baseExposurePct = (baseValue / wallet.equity) * 100;
    }
  }

  return {
    initialCash,
    currentEquity,
    sessionReturnPct,
    sessionPnl,
    peakEquity,
    drawdownPct,
    tradeCount: summary.markers.length,
    buyCount,
    sellCount,
    roundTripCount,
    openBuyLegs,
    firstActivityUnix,
    baseExposurePct,
  };
}

export function buyAndHoldEquity(initialCash: number, entryClose: number, barClose: number): number {
  if (initialCash <= 0 || entryClose <= 0 || barClose <= 0) {
    return initialCash;
  }
  return initialCash * (barClose / entryClose);
}

export function trimBarsFromSessionStart<T extends { timestamp: number | string }>(
  bars: T[],
  sessionStartUnix: number | null,
  paddingBars = 8,
): T[] {
  if (!sessionStartUnix || bars.length === 0) {
    return bars;
  }
  const startIndex = bars.findIndex((bar) => Number(bar.timestamp) >= sessionStartUnix);
  if (startIndex < 0) {
    return bars;
  }
  const from = Math.max(0, startIndex - paddingBars);
  return bars.slice(from);
}

const MIN_BASE_POSITION = 1e-10;

/** Whether the latest paper wallet snapshot holds a non-zero base position. */
export function isLiveSessionInPosition(summary: LiveLogSummary): boolean {
  const base = summary.paperWallet?.base_amount;
  return base != null && Number.isFinite(base) && base > MIN_BASE_POSITION;
}

/** Short position label for chart chrome and job tables. */
export function formatLivePositionLabel(
  summary: LiveLogSummary,
  metrics?: Pick<LiveSessionMetrics, "baseExposurePct">,
): string | null {
  const wallet = summary.paperWallet;
  if (!wallet) {
    return null;
  }
  if (!isLiveSessionInPosition(summary)) {
    return "Flat";
  }
  const exposure =
    metrics?.baseExposurePct ??
    (wallet.equity > 0 && Number.isFinite(wallet.base_amount * wallet.mark_price)
      ? ((wallet.base_amount * wallet.mark_price) / wallet.equity) * 100
      : null);
  if (exposure != null && Number.isFinite(exposure)) {
    const label =
      exposure > 0 && exposure < 0.1 ? "<0.1%" : `${exposure.toFixed(1)}%`;
    return `In position · ${label} in base`;
  }
  return "In position";
}

/** Current session status for live charts (not a full historical timeline). */
export function formatLiveLogPhaseSummary(summary: LiveLogSummary): string | null {
  const parts: string[] = [];
  const optimizerRunning = summary.liveTuneStarted && !summary.liveTuneCompleted;

  if (optimizerRunning) {
    parts.push("Optimizer running");
  } else if (summary.liveTuneCompleted || summary.liveTuneEvents.length > 0) {
    const tune = summary.liveTuneEvents[summary.liveTuneEvents.length - 1];
    if (tune?.status === "ok") {
      const ret =
        tune.return_pct != null
          ? `${tune.return_pct >= 0 ? "+" : ""}${tune.return_pct.toFixed(2)}% in-sample`
          : null;
      const hold =
        tune.holdout_return_pct != null
          ? `${tune.holdout_return_pct >= 0 ? "+" : ""}${tune.holdout_return_pct.toFixed(2)}% holdout`
          : null;
      const metrics = [ret, hold].filter(Boolean).join(" · ");
      parts.push(metrics ? `Optimized (${metrics})` : "Optimized");
    } else if (summary.liveTuneCompleted) {
      parts.push("Optimizer finished");
    }
  }

  const positionLabel = formatLivePositionLabel(summary);
  if (positionLabel) {
    parts.push(positionLabel);
  }

  if (!optimizerRunning) {
    if (summary.markers.length > 0) {
      const fills = countLiveFillStats(summary.markers);
      const roundLabel =
        fills.roundTripCount > 0
          ? `${fills.roundTripCount} round trip${fills.roundTripCount === 1 ? "" : "s"}`
          : null;
      const openLabel = fills.openBuyLegs > 0 ? `${fills.openBuyLegs} open buy` : null;
      const signalLabel = `${fills.buyCount}/${fills.sellCount} buy/sell signals`;
      parts.push([roundLabel, openLabel, signalLabel].filter(Boolean).join(" · "));
    } else if (summary.phases.includes("signals") && summary.terminalBanner) {
      parts.push("Session active");
    } else if (summary.terminalBanner && parts.length === 0) {
      const kind = summary.terminalBanner.terminal === "once" ? "Single check" : "Polling session";
      parts.push(kind);
    }
  }

  if (parts.length === 0) {
    return null;
  }
  return parts.join(" · ");
}
