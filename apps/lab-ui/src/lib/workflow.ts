/** Research loop for overview cards. Nav links to the same pages once. */

export type WorkflowStepId = "overview" | "data" | "lab" | "results";

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
    id: "lab",
    label: "Lab",
    short: "2 · Run",
    description: "Strategy test and compare, forecasts, saved pipelines, and compare charts.",
    href: "/experiments",
    matchPrefixes: ["/experiments", "/actions", "/custom"],
  },
  {
    id: "results",
    label: "Results",
    short: "3 · Review",
    description: "Evaluation runs and configuration snapshots.",
    href: "/runs",
    matchPrefixes: ["/runs", "/configs"],
  },
];

