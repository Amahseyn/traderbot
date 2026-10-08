export type TradeMarker = {
  timestamp: number;
  action: "buy" | "sell";
  price: number;
  mode?: string;
};

export type PaperPortfolioSnapshot = {
  quote_cash: number;
  quote_currency: string;
  base_amount: number;
  equity: number;
  mark_price: number;
};

export type LiveLogSummary = {
  markers: TradeMarker[];
  paperWallet: PaperPortfolioSnapshot | null;
  paperInitialCash: number | null;
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

  for (const line of logText.split("\n")) {
    const row = parseJsonLine(line);
    if (!row) {
      continue;
    }
    const event = row.event;
    if (event === "paper_wallet" && typeof row.initial_cash === "number") {
      paperInitialCash = row.initial_cash;
    }
    if (row.portfolio && typeof row.portfolio === "object") {
      paperWallet = row.portfolio as PaperPortfolioSnapshot;
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
      });
    }
  }

  return { markers, paperWallet, paperInitialCash };
}
