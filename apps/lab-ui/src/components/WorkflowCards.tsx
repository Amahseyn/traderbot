"use client";

import Link from "next/link";
import { WORKFLOW_STEPS } from "@/lib/workflow";

const CARD_STEPS = WORKFLOW_STEPS.filter((step) => step.id !== "overview");

const STEP_ACCENTS = [
  "from-cyan-500/20 to-blue-500/5 ring-cyan-400/20",
  "from-violet-500/20 to-indigo-500/5 ring-violet-400/20",
  "from-emerald-500/20 to-teal-500/5 ring-emerald-400/20",
];

export function WorkflowCards() {
  return (
    <section className="grid gap-4 sm:grid-cols-3" aria-label="Get started">
      {CARD_STEPS.map((step, index) => (
        <Link key={step.id} href={step.href} className="workflow-card group">
          <div
            className={`mb-3 inline-flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br text-xs font-bold text-white ring-1 ${STEP_ACCENTS[index % STEP_ACCENTS.length]}`}
          >
            {index + 1}
          </div>
          <div className="text-[11px] font-semibold uppercase tracking-widest text-accent/90">{step.short}</div>
          <div className="mt-1 text-lg font-semibold text-white transition group-hover:text-accent">
            {step.label}
          </div>
          <p className="mt-2 text-sm leading-relaxed text-muted">{step.description}</p>
          <span className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-accent opacity-0 transition group-hover:opacity-100">
            Open
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
              <path d="M5 12h14M13 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        </Link>
      ))}
    </section>
  );
}
