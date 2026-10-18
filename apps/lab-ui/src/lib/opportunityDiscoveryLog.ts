export type OpportunityDiscoveryRankRow = {
  rank?: number;
  base?: string;
  symbol?: string;
  symbol_key: string;
  resolution: string;
  strategy_id: string;
  preset_hits?: string[];
  trend_score?: number | null;
  trend_score_1d?: number | null;
  trend_score_4h?: number | null;
  pctChange_h24?: number | null;
  volume24h?: number | null;
  regime_label?: string;
  composite_score?: number | null;
  oos_return_pct?: number | null;
  sharpe_ratio?: number | null;
  max_drawdown_pct?: number | null;
  trade_count?: number | null;
  walk_forward_stability?: number | null;
  validation_status?: string;
  rejection_reason?: string | null;
  params_source?: string;
  mean_quote_volume?: number | null;
  volume_percentile?: number | null;
  return_1bar_pct?: number | null;
  return_7bar_pct?: number | null;
  return_30bar_pct?: number | null;
  realized_vol_pct?: number | null;
  range_pct_1bar?: number | null;
  atr_pct?: number | null;
  data_quality?: { error?: string; insufficient_bars?: boolean };
};

export type OpportunityDiscoveryReport = {
  summary?: {
    candidates_evaluated?: number;
    candidates_eligible?: number;
    candidates_rejected?: number;
  };
  config?: {
    scan_kind?: string;
    evaluate_strategies?: boolean;
    exchange?: string;
    months?: number;
    resolutions?: string[];
    trend_sort?: string;
    trend_dir?: string;
    trend_quote?: string;
    screener_presets?: string[];
    detail_top_n?: number;
  };
  trend_scanner?: {
    exchange?: string;
    sort?: string;
    dir?: string;
    total?: number;
    items?: Array<{
      symbol?: string;
      price?: number;
      scores?: Record<string, { score?: number; direction?: string }>;
    }>;
  };
  context?: {
    globals?: {
      fearGreed?: { value?: number; classification?: string };
      avgFunding8hPct?: number | null;
      totalVolume24hUsd?: number | null;
      btcDominance?: number | null;
    };
    sentiment?: Record<string, unknown>;
    structure?: Record<string, unknown>;
  };
  credits?: { estimated_cost?: number; remaining?: number | null };
  screener?: { presets?: Array<{ preset?: { id?: string; label?: string }; meta?: { matched?: number } }> };
  coin_details?: Record<string, unknown>;
  ranked?: OpportunityDiscoveryRankRow[];
  rejected?: OpportunityDiscoveryRankRow[];
  artifact_path?: string;
};

export function isMarketOpportunityRow(row: OpportunityDiscoveryRankRow): boolean {
  return (
    row.params_source === "coinbeacon_market" ||
    row.params_source === "market_scan" ||
    !row.strategy_id?.trim()
  );
}

export function isCoinBeaconDiscoveryReport(report: OpportunityDiscoveryReport | undefined): boolean {
  return report?.config?.scan_kind === "coinbeacon_market";
}

/** Lines to highlight in the job monitor terminal for discovery runs. */
export function extractDiscoveryErrorLogLines(logText: string): string[] {
  if (!logText.trim()) {
    return [];
  }
  const lines = logText.split("\n");
  const picked: string[] = [];
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();
    if (trimmed.startsWith("[lab]")) {
      return [...picked, ...lines.slice(index)];
    }
    if (/^discovery:\s*ERROR\b/i.test(trimmed)) {
      picked.push(line);
    } else if (/^discovery:\s*\d+\s+evaluation error/i.test(trimmed)) {
      picked.push(line);
    }
  }
  return picked;
}

export function parseDiscoveryArtifactPath(logText: string): string | null {
  const match = logText.match(/discovery: wrote (.+discovery_report\.json)/);
  return match?.[1]?.trim() ?? null;
}

export function parseDiscoverySummaryFromLog(logText: string): OpportunityDiscoveryReport["summary"] | null {
  const marker = "discovery: summary ";
  const line = logText
    .split("\n")
    .find((row) => row.includes(marker));
  if (!line) {
    return null;
  }
  const jsonBlock = logText.slice(logText.indexOf('{\n  "candidates_evaluated"'));
  if (!jsonBlock.includes("candidates_evaluated")) {
    return null;
  }
  try {
    const end = jsonBlock.indexOf("\n}\n");
    const slice = end > 0 ? jsonBlock.slice(0, end + 2) : jsonBlock;
    return JSON.parse(slice) as OpportunityDiscoveryReport["summary"];
  } catch {
    return null;
  }
}
