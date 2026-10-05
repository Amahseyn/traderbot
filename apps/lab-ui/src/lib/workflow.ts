/** Research loop for overview cards. Nav links to the same pages once. */

export type WorkflowStepId = "overview" | "data" | "research" | "results";

export type WorkflowStep = {
  id: WorkflowStepId;
  label: string;
  short: string;
  description: string;
  href: string;
  /** Path prefixes that highlight this step (excluding overview). */
  matchPrefixes: string[];
};

export const WORKFLOW_STEPS: WorkflowStep[] = [
  {
    id: "overview",
    label: "Overview",
    short: "Start",
    description: "Health, stats, and shortcuts into the research loop.",
    href: "/",
    matchPrefixes: [],
  },
  {
    id: "data",
    label: "Data",
    short: "1 · Data",
    description: "Sync markets, export OHLC, and browse catalog datasets.",
    href: "/data",
    matchPrefixes: ["/data"],
  },
  {
    id: "research",
    label: "Custom research",
    short: "2 · Research",
    description: "Export, multi-dataset backtests, strategy compare, and sweeps.",
    href: "/custom",
    matchPrefixes: ["/custom", "/actions"],
  },
  {
    id: "results",
    label: "Results",
    short: "3 · Review",
    description: "Backtest runs with metrics, trade logs, and charts.",
    href: "/runs",
    matchPrefixes: ["/runs"],
  },
];

