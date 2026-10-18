/** Parsed tail summary from a completed custom-research job log. */

export type CustomResearchCompareBenchmark = {
  csv: string;
  best_strategy_id?: string | null;
  best_return_pct?: number | null;
  buy_and_hold_return_pct?: number | null;
  strategies_count?: number;
  strategies_beat_buy_hold?: number;
};

export type CustomResearchJobSummary = {
  compare: CustomResearchCompareBenchmark[];
};

function parseJsonObject(line: string): Record<string, unknown> | null {
  const trimmed = line.trim();
  if (!trimmed.startsWith("{")) {
    return null;
  }
  try {
    const row = JSON.parse(trimmed) as unknown;
    return row && typeof row === "object" ? (row as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/** Last JSON summary block in the job log (custom pipeline final `log(json.dumps(summary))`). */
export function parseCustomResearchJobSummary(logText: string): CustomResearchJobSummary | null {
  let best: CustomResearchJobSummary | null = null;
  for (const line of logText.split("\n")) {
    const row = parseJsonObject(line);
    if (!row || !Array.isArray(row.compare)) {
      continue;
    }
    const compare: CustomResearchCompareBenchmark[] = [];
    for (const entry of row.compare) {
      if (!entry || typeof entry !== "object") {
        continue;
      }
      const record = entry as Record<string, unknown>;
      compare.push({
        csv: String(record.csv ?? ""),
        best_strategy_id:
          typeof record.best_strategy_id === "string" ? record.best_strategy_id : null,
        best_return_pct: typeof record.best_return_pct === "number" ? record.best_return_pct : null,
        buy_and_hold_return_pct:
          typeof record.buy_and_hold_return_pct === "number"
            ? record.buy_and_hold_return_pct
            : null,
        strategies_count:
          typeof record.strategies_count === "number" ? record.strategies_count : undefined,
        strategies_beat_buy_hold:
          typeof record.strategies_beat_buy_hold === "number"
            ? record.strategies_beat_buy_hold
            : undefined,
      });
    }
    if (compare.length > 0) {
      best = { compare };
    }
  }
  return best;
}
