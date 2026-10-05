import type { PipelineSpecRow } from "@/lib/api";

export type PipelineGroup = {
  id: string;
  title: string;
  summary: string;
  pipelineIds: string[];
};

export const PIPELINE_GROUPS: PipelineGroup[] = [
  {
    id: "download",
    title: "Download prices",
    summary: "Pull OHLC from Nobitex into the catalog.",
    pipelineIds: ["crypto-jobs-export"],
  },
  {
    id: "strategies",
    title: "Compare strategies",
    summary: "Rule-based backtests on catalog OHLC files.",
    pipelineIds: ["sma-backtest"],
  },
  {
    id: "full",
    title: "Full pipelines",
    summary: "Download jobs, then compare strategies on hourly files already on disk.",
    pipelineIds: ["full-research-strategies", "crypto-1h-local"],
  },
];

const PIPELINE_LABELS: Record<string, { title: string; detail: string }> = {
  "crypto-jobs-export": {
    title: "Crypto 1h jobs",
    detail: "Writes OHLC from the default export jobs file.",
  },
  "sma-backtest": {
    title: "SMA cross",
    detail: "One moving-average strategy on one file.",
  },
  "crypto-1h-local": {
    title: "All strategies on hourly files",
    detail: "Uses the hourly CSVs already on disk and compares rule-based strategies.",
  },
  "full-research-strategies": {
    title: "Download, then strategies only",
    detail: "Exports crypto 1h jobs, then compares rule-based strategies on each hourly file.",
  },
};

export const HORIZON_MINUTES: Record<string, number> = {
  "1m": 1,
  "5m": 5,
  "1h": 60,
  "2h": 120,
  "4h": 240,
  "6h": 360,
  "12h": 720,
  "1d": 1440,
};

export function horizonChoicesForCandle(
  candleMinutes: number,
  options?: { includeUsual?: boolean; includeAll?: boolean },
) {
  const includeUsual = options?.includeUsual ?? true;
  const includeAll = options?.includeAll ?? false;
  return HORIZON_OPTIONS.filter((option) => {
    if (option.value === "usual") return includeUsual;
    if (option.value === "all") return includeAll;
    const target = HORIZON_MINUTES[option.value];
    return target != null && candleMinutes > 0 && target % candleMinutes === 0;
  });
}

export function horizonBarsForChoice(label: string, candleMinutes: number): number {
  if (label === "usual" || label === "") {
    return Math.max(1, Math.round(60 / candleMinutes));
  }
  if (label === "all") {
    return 1;
  }
  const target = HORIZON_MINUTES[label];
  if (!target || candleMinutes <= 0) {
    return 1;
  }
  return Math.max(1, Math.round(target / candleMinutes));
}

export const HORIZON_OPTIONS = [
  { value: "usual", label: "Usual for candle size" },
  { value: "all", label: "Every default horizon" },
  { value: "1m", label: "1 minute ahead" },
  { value: "5m", label: "5 minutes ahead" },
  { value: "1h", label: "1 hour ahead" },
  { value: "2h", label: "2 hours ahead" },
  { value: "4h", label: "4 hours ahead" },
  { value: "6h", label: "6 hours ahead" },
  { value: "12h", label: "12 hours ahead" },
  { value: "1d", label: "1 day ahead" },
] as const;

const HOURLY_HORIZON_OPTIONS = HORIZON_OPTIONS.filter(
  (option) => option.value !== "all" && option.value !== "1m" && option.value !== "5m",
);

function horizonInput(
  defaultValue: string,
  choices: readonly { value: string; label: string }[] = HORIZON_OPTIONS,
): NonNullable<PipelineSpecRow["inputs"]>[number] {
  return {
    key: "horizon",
    label: "Horizon",
    kind: "select",
    default: defaultValue,
    options: choices.map((option) => ({ value: option.value, label: option.label })),
    hint: "How far ahead to evaluate when a pipeline supports a horizon choice.",
  };
}

export function pipelineLabel(pipeline: PipelineSpecRow): { title: string; detail: string } {
  const known = PIPELINE_LABELS[pipeline.id];
  if (known) {
    return known;
  }
  return { title: pipeline.title, detail: pipeline.description };
}

export function isFullPipeline(pipeline: PipelineSpecRow): boolean {
  return pipeline.full === true;
}

export function groupPipelineList(pipelines: PipelineSpecRow[]) {
  const claimed = new Set<string>();
  const grouped = PIPELINE_GROUPS.map((group) => {
    const rows = group.pipelineIds.flatMap((id) => {
      const row = pipelines.find((pipeline) => pipeline.id === id);
      if (!row || claimed.has(id)) return [];
      claimed.add(id);
      return [row];
    });
    return { group, pipelines: rows };
  }).filter((entry) => entry.pipelines.length > 0);

  const rest = pipelines.filter((pipeline) => !claimed.has(pipeline.id));
  if (rest.length > 0) {
    grouped.push({
      group: {
        id: "other",
        title: "Other",
        summary: "Saved configs whose pipeline id is not in the current registry.",
        pipelineIds: rest.map((pipeline) => pipeline.id),
      },
      pipelines: rest,
    });
  }
  return grouped;
}

/** Mirrors `traderbot.pipelines.registry` — used when Lab API is older than the UI. */
export const BUILTIN_PIPELINE_SPECS: PipelineSpecRow[] = [
  {
    id: "crypto-jobs-export",
    title: "Export crypto 1h jobs",
    description: "Nobitex OHLC from export jobs JSON → data/crypto.",
    steps: [
      { id: "export", title: "Download jobs file" },
      { id: "write", title: "Write OHLC files" },
    ],
    inputs: [{ key: "days", label: "Days", kind: "number", default: "90", hint: "How many days of OHLC to pull from Nobitex." }],
  },
  {
    id: "sma-backtest",
    title: "SMA backtest",
    description: "Rule-based SMA cross backtest on one CSV.",
    steps: [
      { id: "load", title: "Load one file" },
      { id: "backtest", title: "SMA cross" },
      { id: "summary", title: "Write summary" },
    ],
    inputs: [
      { key: "dataset", label: "Price file", kind: "dataset", required: true },
      { key: "fast", label: "Fast window", kind: "number", default: "5", hint: "Short moving average, in bars." },
      { key: "slow", label: "Slow window", kind: "number", default: "20", hint: "Long moving average, in bars." },
    ],
  },
  {
    id: "crypto-1h-local",
    title: "Crypto 1h local (no export)",
    description: "Full on-disk *_60.csv per asset; compare all rule-based strategies.",
    steps: [
      { id: "slice", title: "Hourly files on disk" },
      { id: "compare", title: "Compare strategies" },
    ],
    inputs: [
      {
        key: "all_assets",
        label: "Every hourly file",
        kind: "boolean",
        default: "true",
        hint: "Uses *_60.csv already under data/. Uncheck to pick one file.",
      },
      { key: "dataset", label: "Hourly file", kind: "dataset", hint: "Used only when “Every hourly file” is off." },
      horizonInput("1h", HOURLY_HORIZON_OPTIONS),
    ],
    full: true,
  },
  {
    id: "full-research-strategies",
    title: "Download, then strategies only",
    description: "Export crypto 1h jobs, then compare rule-based strategies on each hourly file.",
    full: true,
    steps: [
      { id: "export", title: "Download jobs file" },
      { id: "compare", title: "Compare strategies" },
    ],
    inputs: [
      {
        key: "days",
        label: "Export days",
        kind: "number",
        default: "30",
        hint: "Download window before the strategy compare.",
      },
      {
        key: "all_assets",
        label: "Every hourly file",
        kind: "boolean",
        default: "true",
        hint: "After the download, compare every hourly file. Uncheck to pick one.",
      },
      { key: "dataset", label: "Hourly file", kind: "dataset", hint: "Used only when “Every hourly file” is off." },
    ],
  },
];

function mergePipelineInputs(
  live: PipelineSpecRow["inputs"],
  fallback: PipelineSpecRow["inputs"],
): PipelineSpecRow["inputs"] {
  const byKey = new Map((fallback ?? []).map((field) => [field.key, field]));
  for (const field of live ?? []) byKey.set(field.key, field);
  const ordered: NonNullable<PipelineSpecRow["inputs"]> = [];
  const seen = new Set<string>();
  for (const field of live ?? []) {
    if (seen.has(field.key)) continue;
    seen.add(field.key);
    ordered.push(byKey.get(field.key) ?? field);
  }
  for (const field of fallback ?? []) {
    if (seen.has(field.key)) continue;
    seen.add(field.key);
    ordered.push(field);
  }
  return ordered;
}

export function catalogPipelines(live: PipelineSpecRow[] | undefined): PipelineSpecRow[] {
  if (!live?.length) {
    return BUILTIN_PIPELINE_SPECS;
  }
  const fallbackById = new Map(BUILTIN_PIPELINE_SPECS.map((row) => [row.id, row]));
  const merged = live.map((row) => {
    const fallback = fallbackById.get(row.id);
    if (!fallback) {
      return row;
    }
    return {
      ...fallback,
      ...row,
      inputs: mergePipelineInputs(row.inputs, fallback.inputs),
    };
  });
  const liveIds = new Set(live.map((row) => row.id));
  for (const row of BUILTIN_PIPELINE_SPECS) {
    if (!liveIds.has(row.id)) {
      merged.push(row);
    }
  }
  return merged;
}
