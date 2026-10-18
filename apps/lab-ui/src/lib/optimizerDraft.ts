const SWEEP_DRAFT_KEY = "traderbot.lab.optimizerSweepDraft";
const DRAFT_VERSION = 1;

export type OptimizerSweepDraft = {
  version: typeof DRAFT_VERSION;
  sweepDatasetId: string;
  sweepStrategyId: string;
  sweepParamA: string;
  sweepValuesA: string;
  sweepUseSecondParam: boolean;
  sweepParamB: string;
  sweepValuesB: string;
  sweepCash: string;
  sweepFee: string;
  sweepSelectionMode: "validation" | "in_sample";
  sweepHoldout: string;
  sweepMinTrades: string;
  sweepMaxCombos: string;
  sweepFullGrid: boolean;
  sweepOptimizeMethod: "grid" | "optuna";
  sweepOptunaTrials: string;
};

export function loadOptimizerSweepDraft(): OptimizerSweepDraft | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(SWEEP_DRAFT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<OptimizerSweepDraft>;
    if (parsed.version !== DRAFT_VERSION) return null;
    return parsed as OptimizerSweepDraft;
  } catch {
    return null;
  }
}

export function saveOptimizerSweepDraft(draft: OptimizerSweepDraft): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(SWEEP_DRAFT_KEY, JSON.stringify({ ...draft, version: DRAFT_VERSION }));
  } catch {
    /* ignore quota */
  }
}
