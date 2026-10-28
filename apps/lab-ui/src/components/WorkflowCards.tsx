"use client";

import Link from "next/link";

function StepIcon({ id }: { id: string }) {
  if (id === "data") {
    return (
      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
        <ellipse cx="12" cy="6" rx="8" ry="3" />
        <path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
      </svg>
    );
  }
  if (id === "research") {
    return (
      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
        <path d="M9 3h6l1 7H8L9 3zM7 10h10l-1 11H8L7 10z" strokeLinejoin="round" />
        <path d="M10 14h4" strokeLinecap="round" />
      </svg>
    );
  }
  return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path d="M3 3v18h18" strokeLinecap="round" />
      <path d="M18.5 8.5L13.5 13.5L9.5 9.5L4 15" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const WORKFLOW_MODULES = [
  {
    id: "data",
    tag: "DATA INGESTION",
    href: "/data",
    label: "Market Data & Catalogs",
    description: "Export 1m/coarse OHLC bars, verify timestamp causality, and browse local datasets.",
    action: "Explore data",
  },
  {
    id: "research",
    tag: "RESEARCH PIPELINE",
    href: "/custom",
    label: "Custom Research & Sweeps",
    description: "Multi-dataset backtesting, parameter sweeps, and strategy comparisons.",
    action: "Configure pipeline",
  },
  {
    id: "runs",
    tag: "RUN ARCHIVE",
    href: "/runs",
    label: "Catalog Runs & Logs",
    description: "Inspect trade logs, equity curves, directional accuracy, and performance metrics.",
    action: "View all runs",
  },
];

export function WorkflowCards() {
  return (
    <section className="grid gap-3 sm:grid-cols-3" aria-label="Research workflow steps">
      {WORKFLOW_MODULES.map((item) => {
        return (
          <Link
            key={item.id}
            href={item.href}
            className="workflow-card group flex flex-col justify-between"
          >
            <div>
              <div className="flex items-center justify-between mb-3">
                <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-accent border border-accent/25 bg-accent/10 rounded px-1.5 py-0.5">
                  {item.tag}
                </span>
                <div className="flex h-7 w-7 items-center justify-center rounded border border-border bg-panel-elevated text-zinc-400 transition-colors duration-150 group-hover:border-border-bright group-hover:text-accent">
                  <StepIcon id={item.id} />
                </div>
              </div>
              <h3 className="text-sm font-semibold text-white tracking-tight group-hover:text-accent transition-colors duration-150 sm:text-base">
                {item.label}
              </h3>
              <p className="mt-1.5 text-xs leading-relaxed text-muted">{item.description}</p>
            </div>

            <div className="mt-4 flex items-center gap-1 font-mono text-[11px] font-medium text-muted transition-colors duration-150 group-hover:text-accent">
              <span>{item.action}</span>
              <span aria-hidden>→</span>
            </div>
          </Link>
        );
      })}
    </section>
  );
}
